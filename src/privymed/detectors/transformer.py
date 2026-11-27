"""Fine-tuned transformer token classifier as a PrivyMed detector (Milestone 4)."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from privymed.config import find_repo_root
from privymed.detectors.base import Detector
from privymed.schema import Span

DEFAULT_CHECKPOINT = Path("models/best")


class TransformerDetector(Detector):
    """Loads a checkpoint written by ``privymed-train`` and predicts character spans.

    ``detect_batch`` runs true batched inference; ``detect`` is a batch of one.
    """

    name = "transformer"
    prefers_batch = True  # evaluate with the same batching as training-time dev selection

    def __init__(
        self,
        checkpoint: Path | str = DEFAULT_CHECKPOINT,
        device: str | None = None,
        batch_size: int = 32,
    ) -> None:
        path = Path(checkpoint)
        self.checkpoint = path if path.is_absolute() else find_repo_root() / path
        self.device_name = device
        self.batch_size = batch_size
        self._runner: Any = None
        self._lock = threading.Lock()

    @property
    def runner(self) -> Any:
        if self._runner is None:
            with self._lock:
                if self._runner is None:
                    self._runner = self._load()
        return self._runner

    def _load(self) -> Any:
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        from privymed.training.inference import TokenClassifierRunner

        if not (self.checkpoint / "config.json").is_file():
            raise FileNotFoundError(
                f"no checkpoint at {self.checkpoint} (train with privymed-train)"
            )
        device = torch.device(self.device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
        tokenizer = AutoTokenizer.from_pretrained(self.checkpoint, use_fast=True)
        model = AutoModelForTokenClassification.from_pretrained(
            self.checkpoint, dtype=torch.float32
        ).to(device)
        record = self._record()
        cfg = record.get("config", {})
        return TokenClassifierRunner(
            model,
            tokenizer,
            device,
            max_length=int(cfg.get("max_length", 512)),
            stride=int(cfg.get("stride", 64)),
            batch_size=self.batch_size,
            source=self.name,
        )

    def _record(self) -> dict[str, Any]:
        path = self.checkpoint / "privymed_train_record.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def config(self) -> dict[str, Any]:
        record = self._record()
        return {
            "checkpoint": self.checkpoint.as_posix(),
            "run_name": record.get("run_name"),
            "model_name": record.get("config", {}).get("model_name"),
            "train_git": record.get("git"),
            "device": str(self.runner.device),
            "inference": {
                "dtype": "float32",
                "max_length": self.runner.max_length,
                "stride": self.runner.stride,
                "batch_size": self.runner.batch_size,
            },
        }

    def _detect(self, text: str) -> list[Span]:
        return list(self.runner.predict([text])[0])

    def detect_batch(self, texts: Sequence[str]) -> list[list[Span]]:
        from privymed.schema import span_sort_key, validate_spans_against_text

        out = []
        for text, spans in zip(texts, self.runner.predict(list(texts)), strict=True):
            validate_spans_against_text(text, spans)
            out.append(sorted(spans, key=span_sort_key))
        return out
