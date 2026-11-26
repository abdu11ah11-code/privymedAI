from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from privymed.data_generation.dataset import (
    SPLITS,
    DataConfig,
    SplitName,
    SplitSizes,
    assign_splits,
    build_dataset,
    load_data_config,
    verify_manifest,
)
from privymed.data_generation.families import FAMILIES, FAMILIES_BY_ID
from privymed.io import read_documents
from privymed.schema import EntityType

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def assignment() -> dict[str, SplitName]:
    return assign_splits(FAMILIES, split_seed=7)[0]


def _small_cfg(version: str = "t") -> DataConfig:
    return DataConfig(
        version=version,
        seed=1,
        split_seed=7,
        pk_ratio=0.6,
        sizes=SplitSizes(train=60, dev=20, test_id=20),
        bundle_ratio=0.3,
    )


# ------------------------------------------------------------------ assignment
def test_assignment_is_deterministic(assignment: dict[str, SplitName]) -> None:
    assert assign_splits(FAMILIES, split_seed=7)[0] == assignment


def test_every_family_assigned_once(assignment: dict[str, SplitName]) -> None:
    assert set(assignment) == {f.family_id for f in FAMILIES}
    assert set(assignment.values()) == set(SPLITS)


def test_held_out_family_counts(assignment: dict[str, SplitName]) -> None:
    counts = Counter(assignment.values())
    assert counts["test_id"] >= 4 and counts["dev"] >= 4
    assert counts["train"] > counts["test_id"] + counts["dev"]


def test_one_entity_free_family_per_split(assignment: dict[str, SplitName]) -> None:
    free = Counter(assignment[f.family_id] for f in FAMILIES if f.entity_free)
    assert free == {"train": 1, "dev": 1, "test_id": 1}


def test_train_covers_every_doc_type(assignment: dict[str, SplitName]) -> None:
    all_types = {f.doc_type for f in FAMILIES if not f.entity_free}
    train_types = {f.doc_type for f in FAMILIES if assignment[f.family_id] == "train"}
    assert all_types <= train_types


def test_different_seed_gives_different_assignment(assignment: dict[str, SplitName]) -> None:
    assert assign_splits(FAMILIES, split_seed=8)[0] != assignment


# ------------------------------------------------------------------ build
@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, object]]:
    root = tmp_path_factory.mktemp("ds")
    return root, build_dataset(_small_cfg(), root=root)


def _files(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    files = manifest["files"]
    assert isinstance(files, dict)
    return files


def test_sizes_and_split_metadata(built: tuple[Path, dict[str, object]]) -> None:
    root, manifest = built
    for split, info in _files(manifest).items():
        docs = read_documents(root / str(info["path"]))
        assert len(docs) == {"train": 60, "dev": 20, "test_id": 20}[split]
        assert {d.metadata["split"] for d in docs} == {split}


def test_no_cross_split_family_use(built: tuple[Path, dict[str, object]]) -> None:
    root, manifest = built
    assignment = manifest["split_assignment"]
    assert isinstance(assignment, dict)
    for split, info in _files(manifest).items():
        for doc in read_documents(root / str(info["path"])):
            for fid in str(doc.metadata["family"]).split("+"):
                assert assignment[fid] == split, f"{doc.doc_id} uses {fid} from another split"


def test_every_split_has_all_entity_types_at_scale() -> None:
    # The constraint is checked on renders; confirm it holds on real split output too.
    assignment = assign_splits(FAMILIES, split_seed=7)[0]
    for split in SPLITS:
        members = [FAMILIES_BY_ID[f] for f, s in assignment.items() if s == split]
        from privymed.data_generation.dataset import generate_split

        docs = list(generate_split(split, members, 300, _small_cfg()))
        assert {s.label for d in docs for s in d.spans} == set(EntityType), split


def test_build_is_byte_reproducible(tmp_path: Path, built: tuple[Path, dict[str, object]]) -> None:
    _, first = built
    second = build_dataset(_small_cfg(), root=tmp_path)
    for split in SPLITS:
        assert _files(first)[split]["sha256"] == _files(second)[split]["sha256"]


def test_manifest_and_splits_use_lf_line_endings(built: tuple[Path, dict[str, object]]) -> None:
    """Outputs must be byte-identical across OSes (Windows would otherwise write CRLF)."""
    root, manifest = built
    paths = [root / "data" / "manifests" / "t.json"]
    paths += [root / str(info["path"]) for info in _files(manifest).values()]
    for path in paths:
        assert b"\r\n" not in path.read_bytes(), path


def test_verify_manifest_detects_tampering(tmp_path: Path) -> None:
    manifest = build_dataset(_small_cfg("tamper"), root=tmp_path)
    manifest_path = tmp_path / "data" / "manifests" / "tamper.json"
    verify_manifest(manifest_path, root=tmp_path)  # passes untouched
    test_file = tmp_path / str(_files(manifest)["test_id"]["path"])
    test_file.write_text(test_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_manifest(manifest_path, root=tmp_path)


def test_verify_manifest_detects_missing_file(tmp_path: Path) -> None:
    manifest = build_dataset(_small_cfg("missing"), root=tmp_path)
    (tmp_path / str(_files(manifest)["dev"]["path"])).unlink()
    with pytest.raises(FileNotFoundError):
        verify_manifest(tmp_path / "data" / "manifests" / "missing.json", root=tmp_path)


def test_require_clean_refuses_unknown_git_state(tmp_path: Path) -> None:
    # tmp_path is not a git repo -> state unknown -> treated as dirty.
    with pytest.raises(RuntimeError, match="uncommitted"):
        build_dataset(_small_cfg("clean"), root=tmp_path, require_clean=True)


# ------------------------------------------------------------------ configs
@pytest.mark.parametrize("name", ["data_proto.yaml", "data_v1.yaml"])
def test_shipped_configs_load(name: str) -> None:
    cfg = load_data_config(REPO / "configs" / name)
    assert cfg.split_seed == 7


def test_config_rejects_bad_bundle_parts() -> None:
    with pytest.raises(ValueError):
        DataConfig.model_validate(
            {**json.loads(_small_cfg().model_dump_json()), "bundle_parts": [1, 3]}
        )
