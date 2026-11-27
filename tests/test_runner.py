from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from privymed.data_generation.dataset import DataConfig, SplitSizes, build_dataset
from privymed.detectors.base import Detector
from privymed.evaluation.runner import evaluate_system, register, run_detector
from privymed.schema import Document, Span


class _Nothing(Detector):
    name = "nothing"

    def _detect(self, text: str) -> list[Span]:
        return []


@pytest.fixture(scope="module")
def small_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("eval")
    cfg = DataConfig(
        version="t",
        seed=1,
        split_seed=7,
        pk_ratio=0.6,
        sizes=SplitSizes(train=20, dev=20, test_id=20),
        bundle_ratio=0.3,
    )
    build_dataset(cfg, root=root)
    return root


def test_test_split_is_refused_without_final(small_root: Path) -> None:
    with pytest.raises(PermissionError, match="not a development split"):
        evaluate_system("regex", "test_id", small_root / "data/manifests/t.json", small_root)


def test_dev_report_has_all_sections(small_root: Path) -> None:
    report = evaluate_system("regex", "dev", small_root / "data/manifests/t.json", small_root)
    metrics = report["metrics"]
    assert isinstance(metrics, dict)
    assert {"strict", "boundary", "partial", "overlap", "leak_rate"} <= set(metrics)
    assert set(metrics["strict"]["ci95"]) == {"precision", "recall", "f1", "leak_rate"}
    assert report["split"] == "dev" and report["dataset_version"] == "t"


def test_tampered_data_is_refused(small_root: Path, tmp_path: Path) -> None:
    import shutil

    copy = tmp_path / "copy"
    shutil.copytree(small_root, copy)
    dev = copy / "data/synthetic/t/dev.jsonl"
    dev.write_text(dev.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        evaluate_system("regex", "dev", copy / "data/manifests/t.json", copy)


def test_empty_detector_has_full_leak(small_root: Path) -> None:
    register("nothing", _Nothing)
    report = evaluate_system("nothing", "dev", small_root / "data/manifests/t.json", small_root)
    metrics = report["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["leak_rate"] == 1.0
    assert metrics["strict"]["micro"]["tp"] == 0


def test_run_detector_times_every_document() -> None:
    docs = [Document(doc_id=str(i), text="Call 0300-1234567") for i in range(4)]
    preds, latency = run_detector(_Nothing(), docs, warmup=1)
    assert set(preds) == {"0", "1", "2", "3"} and latency.shape == (4,)
    assert (latency >= 0).all()


def test_aliased_test_split_is_refused(small_root: Path, tmp_path: Path) -> None:
    """Review M3-5: a manifest that renames the test file to 'holdout' (or 'dev') must fail."""
    import json
    import shutil

    copy = tmp_path / "alias"
    shutil.copytree(small_root, copy)
    canonical = json.loads((copy / "data/manifests/t.json").read_text(encoding="utf-8"))
    for alias in ("holdout", "dev"):
        evil = {**canonical, "files": {**canonical["files"], alias: canonical["files"]["test_id"]}}
        path = copy / "evil.json"
        path.write_text(json.dumps(evil), encoding="utf-8")
        with pytest.raises(PermissionError):
            evaluate_system("regex", alias, path, copy)


def test_sweep_refuses_test_split(small_root: Path) -> None:
    from privymed.evaluation.runner import sweep

    with pytest.raises(PermissionError):
        sweep("regex", "x", [1.0], small_root / "data/manifests/t.json", small_root, "test_id")


def test_report_records_git_state_and_packages(small_root: Path) -> None:
    report = evaluate_system("regex", "dev", small_root / "data/manifests/t.json", small_root)
    git, packages = report["git"], report["packages"]
    assert isinstance(git, dict) and set(git) == {"commit", "dirty"}
    assert isinstance(packages, dict) and "numpy" in packages


class _Batchy(Detector):
    name = "batchy"
    prefers_batch = True
    batch_size = 3

    def __init__(self) -> None:
        self.batch_calls: list[int] = []

    def _detect(self, text: str) -> list[Span]:
        return []

    def detect_batch(self, texts: Sequence[str]) -> list[list[Span]]:
        self.batch_calls.append(len(texts))
        return [[] for _ in texts]


def test_batch_preferring_detector_gets_the_whole_split_in_one_call() -> None:
    det = _Batchy()
    docs = [Document(doc_id=str(i), text="x") for i in range(7)]
    preds, latency = run_detector(det, docs, warmup=0)
    assert det.batch_calls == [7] and len(preds) == 7 and latency.shape == (7,)
    assert len(set(latency.tolist())) == 1  # mean latency only
