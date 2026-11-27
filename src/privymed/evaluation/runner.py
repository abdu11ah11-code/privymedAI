"""Run a detection system on a dataset split and write a reproducible evaluation report.

Usage::

    uv run privymed-eval --system regex --split dev

Test splits are refused unless ``--final`` is given (Milestone 8 only; CLAUDE.md
rule 3), and even then the dataset manifest is verified first.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from privymed.config import find_repo_root
from privymed.data_generation.dataset import verify_manifest
from privymed.detectors.base import Detector
from privymed.evaluation.metrics import MODES, evaluate
from privymed.io import read_documents
from privymed.logging_utils import get_logger, setup_logging
from privymed.schema import Document, Span

log = get_logger(__name__)
DEV_SPLITS = frozenset({"train", "dev"})  # allowlist: anything else needs --final
MANIFEST_DIR = "data/manifests"  # every frozen manifest here has its test files guarded


Params = dict[str, float]


def _regex(**params: float) -> Detector:
    from privymed.detectors.regex import RegexDetector

    if params:
        raise ValueError("regex takes no parameters")
    return RegexDetector()


def _presidio(**params: float) -> Detector:
    from privymed.detectors.presidio import PresidioDetector

    return PresidioDetector(**params)


# System name -> factory(**params). Imports are lazy so heavy systems load only when asked for.
SYSTEMS: dict[str, Callable[..., Detector]] = {"regex": _regex, "presidio": _presidio}


def register(name: str, factory: Callable[..., Detector]) -> None:
    SYSTEMS[name] = factory


def _parse_params(items: Sequence[str]) -> Params:
    out: Params = {}
    for item in items:
        key, _, value = item.partition("=")
        out[key.strip()] = float(value)
    return out


def _git_state(root: Path) -> dict[str, object]:
    """HEAD commit and whether src/configs had uncommitted changes (review finding M3-6)."""
    try:

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, check=True
            ).stdout.strip()

        commit = git("rev-parse", "--short", "HEAD")
        dirty = bool(git("status", "--porcelain", "--", "src", "configs", "pyproject.toml"))
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "dirty": True}
    return {"commit": commit, "dirty": dirty}


def _package_versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for pkg in ("privymed", "numpy", "scipy", "presidio-analyzer", "spacy", "en-core-web-lg"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            continue
    return out


def _protected_test_hashes(root: Path) -> set[str]:
    """SHA-256 of every non-train/dev file listed in any manifest under data/manifests/."""
    hashes: set[str] = set()
    for path in sorted((root / MANIFEST_DIR).glob("*.json")):
        files = json.loads(path.read_text(encoding="utf-8")).get("files", {})
        hashes |= {info["sha256"] for name, info in files.items() if name not in DEV_SPLITS}
    return hashes


def _guard_split(split: str, file_info: dict[str, str], root: Path, final: bool) -> None:
    """Refuse test data outside the Milestone 8 final evaluation.

    Allowlist by name (only train/dev), and by content: a file whose hash equals a
    frozen test file is refused under any split name (review M3-5: a manifest aliasing
    test_id as "holdout" passed the old name-only blacklist).
    """
    if final:
        return
    if split not in DEV_SPLITS:
        raise PermissionError(
            f"split {split!r} is not a development split: only the Milestone 8 final "
            "evaluation may use it (pass --final). Develop and tune on 'dev'."
        )
    if file_info["sha256"] in _protected_test_hashes(root):
        raise PermissionError(f"split {split!r} contains a frozen test file (hash match)")


def run_detector(
    detector: Detector, docs: Sequence[Document], warmup: int = 5
) -> tuple[dict[str, list[Span]], np.ndarray]:
    """Predict every document; return predictions and per-document latency (ms)."""
    for doc in docs[:warmup]:  # warm caches / lazy model loading outside the timed loop
        detector.detect(doc.text)
    preds: dict[str, list[Span]] = {}
    latency = np.zeros(len(docs))
    for i, doc in enumerate(docs):
        t0 = time.perf_counter()
        preds[doc.doc_id] = detector.detect(doc.text)
        latency[i] = (time.perf_counter() - t0) * 1000
    return preds, latency


def evaluate_system(
    system: str,
    split: str,
    manifest_path: Path,
    root: Path,
    final: bool = False,
    params: Params | None = None,
) -> dict[str, object]:
    params = params or {}
    if split not in DEV_SPLITS and not final:  # fail fast, before reading anything
        _guard_split(split, {"sha256": ""}, root, final)
    verify_manifest(manifest_path, root=root)  # data must match the frozen manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if split not in manifest["files"]:
        raise KeyError(f"split {split!r} not in manifest")
    _guard_split(split, manifest["files"][split], root, final)
    docs = read_documents(root / manifest["files"][split]["path"])

    detector = SYSTEMS[system](**params)
    load_t0 = time.perf_counter()
    detector.detect("warm-up")
    load_ms = (time.perf_counter() - load_t0) * 1000
    preds, latency = run_detector(detector, docs)
    result = evaluate(docs, preds)
    log.info("%s on %s: %d docs evaluated", system, split, len(docs))

    total_s = latency.sum() / 1000
    chars = sum(len(d.text) for d in docs)
    return {
        "system": system,
        "dataset_version": manifest["version"],
        "split": split,
        "params": params,
        "detector_config": detector.config() if hasattr(detector, "config") else {},
        "git": _git_state(root),
        "packages": _package_versions(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "latency_ms_per_doc": {
            "mean": round(float(latency.mean()), 3),
            "p50": round(float(np.percentile(latency, 50)), 3),
            "p95": round(float(np.percentile(latency, 95)), 3),
        },
        "throughput": {
            "docs_per_s": round(len(docs) / total_s, 1) if total_s else None,
            "chars_per_s": round(chars / total_s) if total_s else None,
        },
        "first_call_ms": round(load_ms, 1),
        "metrics": result.summary(bootstrap=True),
    }


def sweep(
    system: str,
    key: str,
    values: Sequence[float],
    manifest_path: Path,
    root: Path,
    split: str = "dev",
) -> dict[str, object]:
    """Evaluate one parameter grid on a *development* split and pick the best strict F1.

    Test splits are always refused: tuning on test is never legitimate.
    """
    if split not in DEV_SPLITS:
        raise PermissionError("parameter sweeps may only use development splits")
    rows = []
    for value in values:
        report = evaluate_system(system, split, manifest_path, root, params={key: value})
        metrics = report["metrics"]
        assert isinstance(metrics, dict)
        rows.append(
            {
                key: value,
                "strict": metrics["strict"]["micro"],
                "overlap_f1": metrics["overlap"]["micro"]["f1"],
                "leak_rate": metrics["leak_rate"],
            }
        )
    best = max(rows, key=lambda r: (r["strict"]["f1"], -r[key]))  # tie -> lower threshold
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "system": system,
        "dataset_version": manifest["version"],
        "split": split,
        "param": key,
        "rows": rows,
        "best": best,
        "git": _git_state(root),
        "packages": _package_versions(),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }


def _print_summary(report: dict[str, object]) -> None:
    metrics = report["metrics"]
    assert isinstance(metrics, dict)
    print(f"{report['system']} on {report['dataset_version']}/{report['split']}")
    for mode in MODES:
        block = metrics[mode]
        m, ci = block["micro"], block["ci95"]["f1"]
        print(
            f"  {mode:<8} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} "
            f"[{ci[0]:.3f}, {ci[1]:.3f}]  macroF1={block['macro_f1']:.3f}"
        )
    print(f"  leak rate {metrics['leak_rate']:.3%}   latency {report['latency_ms_per_doc']}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate a PrivyMed detection system.")
    parser.add_argument("--system", required=True, choices=sorted(SYSTEMS))
    parser.add_argument("--split", default="dev")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/v1.json"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports/eval"))
    parser.add_argument("--final", action="store_true", help="Milestone 8 only: allow test splits")
    parser.add_argument("--param", action="append", default=[], help="detector param key=value")
    parser.add_argument("--sweep", help="dev-only grid, e.g. score_threshold=0.3,0.4,0.5")
    args = parser.parse_args(argv)
    setup_logging("INFO")
    root = find_repo_root()
    if args.sweep:
        key, _, raw = args.sweep.partition("=")
        result = sweep(
            args.system,
            key,
            [float(v) for v in raw.split(",")],
            root / args.manifest,
            root,
            args.split,
        )
        out = root / args.report_dir / f"{args.system}_sweep_{key}_{args.split}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        for row in result["rows"]:  # type: ignore[attr-defined]
            s = row["strict"]
            print(
                f"  {key}={row[key]:<5} strict P={s['precision']:.3f} R={s['recall']:.3f} "
                f"F1={s['f1']:.3f}  leak={row['leak_rate']:.3%}"
            )
        print(f"  best: {key}={result['best'][key]}  report: {out.as_posix()}")  # type: ignore[index]
        return
    params = _parse_params(args.param)
    report = evaluate_system(
        args.system, args.split, root / args.manifest, root, args.final, params
    )
    # Non-default params get their own file, so they never overwrite the canonical report.
    suffix = "".join(f"_{k}{v:g}" for k, v in sorted(params.items()))
    name = f"{args.system}_{report['dataset_version']}_{args.split}{suffix}.json"
    out = (root / args.report_dir / name).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    _print_summary(report)
    print(f"  report: {out.as_posix()}")


if __name__ == "__main__":
    main()
