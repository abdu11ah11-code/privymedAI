"""Build a versioned synthetic dataset: family-level splits, JSONL files, hashed manifest.

Usage::

    uv run privymed-generate --config configs/data_v1.yaml

Split methodology (ADR-006):

* The split unit is the **template family**, never the document, so test-set
  document *structures* are never seen in training.
* Assignment is a seeded random draw under explicit constraints (not a hand
  choice, which would invite "did you pick easy test families?"):
  - in every document type with >= 3 families, one family is held out
    (two if the type has >= 4); held-out families alternate test / dev;
  - entity-free families (one per split) are dealt train / dev / test;
  - train keeps >= 1 family of every document type;
  - every split must contain all entity types (checked by rendering);
    if not, the next seed is tried and the attempt count is recorded.
* Bundles only combine families of the same split.

The manifest (committed) records file SHA-256 hashes; :func:`verify_manifest`
must pass before any final test evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from importlib import metadata
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from privymed.config import find_repo_root
from privymed.data_generation import pools
from privymed.data_generation.engine import (
    TemplateFamily,
    derive_seed,
    generate_bundle,
    generate_document,
)
from privymed.data_generation.entities import EntityFactory
from privymed.data_generation.families import FAMILIES
from privymed.data_generation.noise import CLEAN
from privymed.io import write_documents
from privymed.logging_utils import get_logger, setup_logging
from privymed.schema import Document, EntityType

SplitName = Literal["train", "dev", "test_id"]
SPLITS: tuple[SplitName, ...] = ("train", "dev", "test_id")
_COVERAGE_RENDERS = 60
# Every split: each entity type >= 2.5% of spans (estimated from renders). Measured ceiling with
# the current families is ~3.2% (EMAIL/CNIC are the bottleneck); 2.5% is met by ~8% of draws.
MIN_TYPE_SHARE = 0.025
_MAX_SPLIT_ATTEMPTS = 500

log = get_logger(__name__)


# ============================================================================ config
class SplitSizes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    train: int = Field(ge=1)
    dev: int = Field(ge=1)
    test_id: int = Field(ge=1)


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=r"^[a-z0-9_]+$")
    seed: int = Field(ge=0, le=2**32 - 1)
    split_seed: int = Field(ge=0, le=2**32 - 1)
    pk_ratio: float = Field(ge=0.0, le=1.0)
    sizes: SplitSizes
    bundle_ratio: float = Field(ge=0.0, le=1.0)
    bundle_parts: tuple[int, int] = (2, 3)
    # Same entity-free share in every split, independent of how many families each split has.
    entity_free_ratio: float = Field(default=0.06, ge=0.0, le=1.0)
    output_dir: Path = Path("data/synthetic")
    manifest_dir: Path = Path("data/manifests")

    @model_validator(mode="after")
    def _check_parts(self) -> DataConfig:
        lo, hi = self.bundle_parts
        if not 2 <= lo <= hi:
            raise ValueError("bundle_parts must satisfy 2 <= min <= max")
        return self


def load_data_config(path: Path) -> DataConfig:
    with path.open(encoding="utf-8") as fh:
        return DataConfig.model_validate(yaml.safe_load(fh))


# ============================================================================ split assignment
def _entity_counts(family: TemplateFamily) -> Counter[EntityType]:
    """Per-type span counts over a fixed sample of renders (used for split constraints)."""
    factory = EntityFactory(0)
    return Counter(
        s.label
        for i in range(_COVERAGE_RENDERS)
        for s in generate_document(family, factory, 0, i, noise=CLEAN).spans
    )


def _split_shares(
    members: Sequence[TemplateFamily], counts: dict[str, Counter[EntityType]]
) -> dict[EntityType, float]:
    total: Counter[EntityType] = Counter()
    for f in members:
        total.update(counts[f.family_id])
    n = sum(total.values())
    return {t: (total[t] / n if n else 0.0) for t in EntityType}


def _draw(families: Sequence[TemplateFamily], rng: random.Random) -> dict[str, SplitName]:
    by_type: dict[str, list[TemplateFamily]] = defaultdict(list)
    for fam in sorted(families, key=lambda f: f.family_id):
        by_type[fam.doc_type].append(fam)

    assignment: dict[str, SplitName] = {}
    held_out: list[str] = []
    for doc_type in sorted(by_type):
        group = by_type[doc_type][:]
        rng.shuffle(group)
        if all(f.entity_free for f in group):
            for fam, split in zip(group, SPLITS, strict=False):
                assignment[fam.family_id] = split
            for fam in group[3:]:
                assignment[fam.family_id] = "train"
            continue
        n_hold = 2 if len(group) >= 4 else 1 if len(group) >= 3 else 0
        held_out += [f.family_id for f in group[:n_hold]]
        for fam in group[n_hold:]:
            assignment[fam.family_id] = "train"
    rng.shuffle(held_out)
    for i, fid in enumerate(held_out):
        assignment[fid] = "test_id" if i % 2 == 0 else "dev"
    return assignment


def assign_splits(
    families: Sequence[TemplateFamily], split_seed: int
) -> tuple[dict[str, SplitName], int]:
    """Return ``(family_id -> split, attempts)`` satisfying the coverage constraints."""
    counts = {f.family_id: _entity_counts(f) for f in families}
    doc_types = {f.doc_type for f in families if not f.entity_free}
    for attempt in range(1, _MAX_SPLIT_ATTEMPTS + 1):
        rng = random.Random(derive_seed(split_seed, "split", attempt))
        assignment = _draw(families, rng)
        ok = True
        for split in SPLITS:
            members = [f for f in families if assignment[f.family_id] == split]
            # Every type present with a usable share, so dev can tune and test can measure
            # every type (review finding M2-4: dev ID was 3.0% vs test 15.0%).
            if min(_split_shares(members, counts).values()) < MIN_TYPE_SHARE:
                ok = False
        train_types = {f.doc_type for f in families if assignment[f.family_id] == "train"}
        if ok and doc_types <= train_types:
            return assignment, attempt
    raise RuntimeError(f"no valid split assignment in {_MAX_SPLIT_ATTEMPTS} attempts")


# ============================================================================ split pools
_POOL_SHARES = {"dev": 0.2, "test_id": 0.2}


def partition_pool(
    items: Sequence[str], split_seed: int, name: str
) -> dict[SplitName, tuple[str, ...]]:
    """Deterministically partition a value pool across splits (~60/20/20, each >= 1)."""
    ordered = sorted(items)
    random.Random(derive_seed(split_seed, f"pool:{name}", 0)).shuffle(ordered)
    n_dev = max(1, round(len(ordered) * _POOL_SHARES["dev"]))
    n_test = max(1, round(len(ordered) * _POOL_SHARES["test_id"]))
    if n_dev + n_test >= len(ordered):
        raise ValueError(f"pool {name!r} too small to partition ({len(ordered)} items)")
    return {
        "test_id": tuple(ordered[:n_test]),
        "dev": tuple(ordered[n_test : n_test + n_dev]),
        "train": tuple(ordered[n_test + n_dev :]),
    }


def _is_name_word_negative(sentence: str) -> bool:
    first = re.split(r"[-']", sentence.split()[0])[
        0
    ]  # "Faith-based" -> "Faith", "Bell's" -> "Bell"
    names = set(pools.AMBIG_FIRST_F + pools.AMBIG_FIRST_M + pools.AMBIG_LAST) | {
        "Frank",
        "Bell",
        "Wood",
    }
    return first in names


def split_pools(split_seed: int) -> dict[SplitName, dict[str, tuple[str, ...]]]:
    """Per-split hospital-name cores and narrative sentences.

    Without this, ~94% of test hospital strings also occurred in train (measured on
    the v1 trial build), so HOSPITAL scores would measure memorisation. Name-word
    negatives ("Frank blood ...") and generic sentences are partitioned separately so
    every split gets some of each.
    """
    cores = partition_pool(pools.HOSPITAL_CORES, split_seed, "hospital_cores")
    hard = [s for s in pools.NARRATIVE if _is_name_word_negative(s)]
    generic = [s for s in pools.NARRATIVE if not _is_name_word_negative(s)]
    hard_parts = partition_pool(hard, split_seed, "narrative_hard")
    generic_parts = partition_pool(generic, split_seed, "narrative_generic")
    return {
        split: {
            "hospital_cores": cores[split],
            "narrative": hard_parts[split] + generic_parts[split],
        }
        for split in SPLITS
    }


# ============================================================================ generation
def generate_split(
    split: SplitName,
    families: Sequence[TemplateFamily],
    n_docs: int,
    cfg: DataConfig,
) -> Iterator[Document]:
    """Yield ``n_docs`` documents for one split: singles, same-split bundles, entity-free docs."""
    plan_rng = random.Random(derive_seed(cfg.seed, f"plan:{split}", 0))
    split_pool = split_pools(cfg.split_seed)[split]
    factory = EntityFactory(
        cfg.seed,
        pk_ratio=cfg.pk_ratio,
        hospital_cores=split_pool["hospital_cores"],
        narrative=split_pool["narrative"],
    )
    ordered = sorted(families, key=lambda f: f.family_id)
    pii = [f for f in ordered if not f.entity_free]
    free = [f for f in ordered if f.entity_free]
    lo, hi = cfg.bundle_parts
    for i in range(n_docs):
        r = plan_rng.random()
        if free and r < cfg.entity_free_ratio:
            doc = generate_document(free[i % len(free)], factory, cfg.seed, i)
        elif len(pii) >= lo and r < cfg.entity_free_ratio + cfg.bundle_ratio:
            parts = plan_rng.sample(pii, plan_rng.randint(lo, min(hi, len(pii))))
            doc = generate_bundle(parts, factory, cfg.seed, i)
        else:
            doc = generate_document(pii[i % len(pii)], factory, cfg.seed, i)
        yield Document(
            doc_id=doc.doc_id,
            text=doc.text,
            spans=doc.spans,
            metadata={**doc.metadata, "split": split},
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state(root: Path) -> dict[str, str | bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    "src",
                    "configs",
                    "pyproject.toml",
                    "uv.lock",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "dirty": True}
    return {"commit": commit, "dirty": dirty}


def build_dataset(
    cfg: DataConfig, root: Path | None = None, require_clean: bool = False
) -> dict[str, object]:
    """Generate all splits, write JSONL + manifest, and return the manifest.

    ``require_clean=True`` refuses to run when ``src/`` or ``configs/`` have
    uncommitted changes, so the manifest's commit hash really describes the
    code that produced the data.
    """
    root = root or find_repo_root()
    if require_clean and _git_state(root)["dirty"]:
        raise RuntimeError(
            "uncommitted changes in src/ or configs/: commit first, or pass --allow-dirty"
        )
    out_dir = root / cfg.output_dir / cfg.version
    manifest_path = root / cfg.manifest_dir / f"{cfg.version}.json"
    assignment, attempts = assign_splits(FAMILIES, cfg.split_seed)
    log.info("split assignment found after %d attempt(s)", attempts)

    files: dict[str, dict[str, object]] = {}
    for split in SPLITS:
        members = [f for f in FAMILIES if assignment[f.family_id] == split]
        path = out_dir / f"{split}.jsonl"
        docs = list(generate_split(split, members, getattr(cfg.sizes, split), cfg))
        write_documents(path, docs)
        labels = Counter(s.label.value for d in docs for s in d.spans)
        files[split] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "documents": len(docs),
            "spans": sum(labels.values()),
            "spans_by_type": dict(sorted(labels.items())),
            "families": sorted(f.family_id for f in members),
        }
        log.info("wrote %s: %d docs, %d spans", split, len(docs), sum(labels.values()))

    manifest: dict[str, object] = {
        "version": cfg.version,
        "config": json.loads(cfg.model_dump_json()),
        "split_assignment": dict(sorted(assignment.items())),
        "split_attempts": attempts,
        "files": files,
        "generator": {
            **_git_state(root),
            "python": platform.python_version(),
            "faker": metadata.version("faker"),
            "uv_lock_sha256": sha256_file(root / "uv.lock")
            if (root / "uv.lock").is_file()
            else None,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def verify_manifest(manifest_path: Path, root: Path | None = None) -> None:
    """Raise if any split file is missing or its SHA-256 differs from the manifest."""
    root = root or find_repo_root()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for split, info in manifest["files"].items():
        path = root / info["path"]
        if not path.is_file():
            raise FileNotFoundError(
                f"{split}: {path} missing (regenerate with the manifest config)"
            )
        actual = sha256_file(path)
        if actual != info["sha256"]:
            raise ValueError(f"{split}: hash mismatch - data changed since manifest was frozen")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the PrivyMed synthetic dataset.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--allow-dirty", action="store_true", help="allow generation from uncommitted code"
    )
    args = parser.parse_args(argv)
    setup_logging("INFO")
    manifest = build_dataset(load_data_config(args.config), require_clean=not args.allow_dirty)
    files = manifest["files"]
    assert isinstance(files, dict)
    for split, info in files.items():
        digest = str(info["sha256"])[:12]
        print(f"{split:<8} {info['documents']:>6} docs  {info['spans']:>7} spans  {digest}")


if __name__ == "__main__":
    main()
