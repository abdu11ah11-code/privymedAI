"""Fine-tune a transformer token classifier on dataset v1 train; select on dev.

Usage::

    uv run privymed-train --config configs/train/distilbert.yaml

Writes the best checkpoint to ``models/<run_name>/`` (git-ignored) and a run
record to ``reports/train/<run_name>.json`` (committed): config, seed,
environment, git state, per-epoch train loss / dev loss / dev span metrics,
duration and peak GPU memory. Test splits are never loaded here.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
import yaml
from pydantic import BaseModel, ConfigDict, Field

from privymed.config import find_repo_root
from privymed.data_generation.dataset import verify_manifest
from privymed.evaluation.metrics import evaluate
from privymed.evaluation.runner import _git_state, _package_versions
from privymed.io import read_documents
from privymed.logging_utils import get_logger, setup_logging
from privymed.repro import set_global_seed
from privymed.schema import Document
from privymed.training.alignment import ID2LABEL, IGNORE, LABEL2ID
from privymed.training.data import Encoded, encode_documents
from privymed.training.inference import TokenClassifierRunner

log = get_logger(__name__)
Precision = Literal["bf16", "fp32"]


class TrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    run_name: str = Field(pattern=r"^[A-Za-z0-9_.\-]+$")
    model_name: str
    manifest: Path = Path("data/manifests/v1.json")
    max_length: int = Field(default=512, ge=32, le=512)
    stride: int = Field(default=64, ge=0)
    batch_size: int = Field(default=16, ge=1)
    grad_accum: int = Field(default=1, ge=1)
    eval_batch_size: int = Field(default=32, ge=1)
    lr: float = Field(default=5e-5, gt=0)
    weight_decay: float = Field(default=0.01, ge=0)
    warmup_ratio: float = Field(default=0.1, ge=0, le=1)
    max_grad_norm: float = Field(default=1.0, gt=0)
    epochs: int = Field(default=4, ge=1)
    patience: int = Field(default=2, ge=1)
    seed: int = Field(default=13, ge=0)
    precision: Precision = "bf16"
    max_train_docs: int | None = None  # for smoke tests only
    max_dev_docs: int | None = None
    output_dir: Path = Path("models")
    report_dir: Path = Path("reports/train")


def load_train_config(path: Path) -> TrainConfig:
    with path.open(encoding="utf-8") as fh:
        return TrainConfig.model_validate(yaml.safe_load(fh))


def linear_warmup_decay(
    optimizer: torch.optim.Optimizer, warmup_steps: int, total_steps: int
) -> torch.optim.lr_scheduler.LambdaLR:
    """Learning rate rises linearly from 0 over ``warmup_steps``, then decays linearly to 0."""

    def factor(step: int) -> float:
        if step < warmup_steps:
            return step / max(1, warmup_steps)
        return max(0.0, (total_steps - step) / max(1, total_steps - warmup_steps))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, factor)


def _collate(tokenizer: Any, items: Sequence[Encoded]) -> dict[str, torch.Tensor]:
    """Dynamic padding: pad to the longest window in the batch, labels with IGNORE."""
    longest = max(len(e.input_ids) for e in items)
    pad = tokenizer.pad_token_id or 0
    ids = torch.full((len(items), longest), pad, dtype=torch.long)
    mask = torch.zeros((len(items), longest), dtype=torch.long)
    labels = torch.full((len(items), longest), IGNORE, dtype=torch.long)
    for i, e in enumerate(items):
        n = len(e.input_ids)
        ids[i, :n] = torch.tensor(e.input_ids)
        mask[i, :n] = torch.tensor(e.attention_mask)
        labels[i, :n] = torch.tensor(e.labels)
    return {"input_ids": ids, "attention_mask": mask, "labels": labels}


def _batches(items: Sequence[Encoded], size: int, rng: random.Random | None) -> list[list[Encoded]]:
    order = list(range(len(items)))
    if rng is not None:
        rng.shuffle(order)
    return [[items[i] for i in order[b : b + size]] for b in range(0, len(order), size)]


def _dev_loss(
    model: Any, tokenizer: Any, windows: Sequence[Encoded], cfg: TrainConfig, device: torch.device
) -> float:
    model.eval()
    total, n = 0.0, 0
    with torch.inference_mode():
        for batch in _batches(windows, cfg.eval_batch_size, None):
            t = {k: v.to(device) for k, v in _collate(tokenizer, batch).items()}
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=_amp(cfg, device)):
                out = model(**t)
            total += float(out.loss) * len(batch)
            n += len(batch)
    return total / max(n, 1)


def _amp(cfg: TrainConfig, device: torch.device) -> bool:
    return cfg.precision == "bf16" and device.type == "cuda"


def train(
    cfg: TrainConfig, root: Path | None = None, require_clean: bool = False
) -> dict[str, object]:
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    root = root or find_repo_root()
    manifest_path = root / cfg.manifest
    verify_manifest(manifest_path, root=root)
    files = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
    train_docs: list[Document] = read_documents(root / files["train"]["path"])
    dev_docs: list[Document] = read_documents(root / files["dev"]["path"])
    if cfg.max_train_docs:
        train_docs = train_docs[: cfg.max_train_docs]
    if cfg.max_dev_docs:
        dev_docs = dev_docs[: cfg.max_dev_docs]

    # Capture the code state at the START (files edited during a run must not be recorded
    # as the run's code; E-003 preliminary run showed dirty=True from later edits).
    git_at_start = _git_state(root)
    if require_clean and git_at_start["dirty"]:
        raise RuntimeError(
            "uncommitted changes in src/configs: commit first, or pass --allow-dirty"
        )
    set_global_seed(cfg.seed)
    rng = random.Random(cfg.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(cfg.model_name, use_fast=True)
    train_windows, train_rep = encode_documents(tokenizer, train_docs, cfg.max_length, cfg.stride)
    dev_windows, _ = encode_documents(tokenizer, dev_docs, cfg.max_length, cfg.stride)
    log.info(
        "train windows=%d (docs=%d), dev docs=%d",
        len(train_windows),
        len(train_docs),
        len(dev_docs),
    )

    model = AutoModelForTokenClassification.from_pretrained(
        cfg.model_name, num_labels=len(ID2LABEL), id2label=ID2LABEL, label2id=LABEL2ID
    ).to(device)
    no_decay = ("bias", "LayerNorm.weight", "layernorm", "layer_norm")
    groups = [
        {"params": [p for n, p in model.named_parameters() if not any(k in n for k in no_decay)],
         "weight_decay": cfg.weight_decay},
        {"params": [p for n, p in model.named_parameters() if any(k in n for k in no_decay)],
         "weight_decay": 0.0},
    ]  # fmt: skip
    optimizer = torch.optim.AdamW(groups, lr=cfg.lr)
    steps_per_epoch = math.ceil(len(train_windows) / (cfg.batch_size * cfg.grad_accum))
    total_steps = steps_per_epoch * cfg.epochs
    scheduler = linear_warmup_decay(optimizer, int(cfg.warmup_ratio * total_steps), total_steps)
    runner = TokenClassifierRunner(
        model, tokenizer, device, cfg.max_length, cfg.stride, cfg.eval_batch_size
    )

    out_dir = root / cfg.output_dir / cfg.run_name
    history: list[dict[str, object]] = []
    best_f1, best_epoch, bad_epochs = -1.0, 0, 0
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    t_start = time.perf_counter()
    for epoch in range(1, cfg.epochs + 1):
        model.train()
        t_epoch = time.perf_counter()
        losses: list[float] = []
        batches = _batches(train_windows, cfg.batch_size, rng)
        for step, batch in enumerate(batches, start=1):
            t = {k: v.to(device) for k, v in _collate(tokenizer, batch).items()}
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=_amp(cfg, device)):
                loss = model(**t).loss / cfg.grad_accum
            loss.backward()
            losses.append(loss.item() * cfg.grad_accum)
            if step % cfg.grad_accum == 0 or step == len(batches):
                torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.max_grad_norm)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
        dev_loss = _dev_loss(model, tokenizer, dev_windows, cfg, device)
        preds = runner.predict([d.text for d in dev_docs])
        res = evaluate(dev_docs, {d.doc_id: p for d, p in zip(dev_docs, preds, strict=True)})
        strict, overlap = res.micro("strict"), res.micro("overlap")
        row = {
            "epoch": epoch,
            "train_loss": round(float(np.mean(losses)), 5),
            "dev_loss": round(dev_loss, 5),
            "dev_strict": strict.as_dict(),
            "dev_overlap_f1": round(overlap.f1, 4),
            "dev_macro_f1": round(res.macro_f1("strict"), 4),
            "dev_leak_rate": round(res.leak_rate, 4),
            "epoch_seconds": round(time.perf_counter() - t_epoch, 1),
        }
        history.append(row)
        log.info("epoch %d train_loss=%.4f dev_loss=%.4f dev_strict_f1=%.4f leak=%.4f",
                 epoch, row["train_loss"], dev_loss, strict.f1, res.leak_rate)  # fmt: skip
        if strict.f1 > best_f1:
            best_f1, best_epoch, bad_epochs = strict.f1, epoch, 0
            out_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out_dir)
            tokenizer.save_pretrained(out_dir)
        else:
            bad_epochs += 1
            if bad_epochs >= cfg.patience:
                log.info("early stopping after epoch %d", epoch)
                break

    peak = torch.cuda.max_memory_allocated() / 2**30 if device.type == "cuda" else None
    record: dict[str, object] = {
        "run_name": cfg.run_name,
        "config": json.loads(cfg.model_dump_json()),
        "dataset": json.loads(manifest_path.read_text(encoding="utf-8"))["version"],
        "train_documents": len(train_docs),
        "train_windows": len(train_windows),
        "alignment": {
            "straddling": train_rep.stats.straddling,
            "unlabelled_spans": train_rep.stats.unlabelled_spans,
        },
        "best_epoch": best_epoch,
        "best_dev_strict_f1": round(best_f1, 4),
        "history": history,
        "train_seconds": round(time.perf_counter() - t_start, 1),
        "peak_gpu_memory_gib": round(peak, 2) if peak is not None else None,
        "device": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
        "checkpoint": (cfg.output_dir / cfg.run_name).as_posix(),
        "git": git_at_start,
        "packages": {**_package_versions(), "torch": torch.__version__},
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    report = root / cfg.report_dir / f"{cfg.run_name}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "privymed_train_record.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return record


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fine-tune a PrivyMed token classifier.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed", type=int, help="override the config seed")
    parser.add_argument("--run-name", help="override the config run_name")
    parser.add_argument("--allow-dirty", action="store_true", help="allow uncommitted code")
    args = parser.parse_args(argv)
    setup_logging("INFO")
    cfg = load_train_config(args.config)
    updates: dict[str, object] = {}
    if args.seed is not None:
        updates["seed"] = args.seed
    if args.run_name:
        updates["run_name"] = args.run_name
    if updates:
        cfg = TrainConfig.model_validate({**cfg.model_dump(), **updates})
    record = train(cfg, require_clean=not args.allow_dirty)
    print(
        f"{record['run_name']}: best dev strict F1 {record['best_dev_strict_f1']} at epoch "
        f"{record['best_epoch']}, {record['train_seconds']} s, "
        f"peak GPU {record['peak_gpu_memory_gib']} GiB"
    )


if __name__ == "__main__":
    main()
