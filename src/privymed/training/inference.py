"""Run a token-classification model over documents and return character spans.

Long documents are split into overlapping windows (``max_length`` / ``stride``).
A token that appears in several windows keeps the prediction from the window in
which it sits farthest from a window edge, i.e. with the most context on both
sides. Merged per-token predictions are then decoded into spans.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import torch

from privymed.schema import Span
from privymed.training.alignment import IGNORE, Offset, clean_offsets, labels_to_spans


@dataclass(frozen=True)
class TokenPrediction:
    offset: Offset
    label_id: int
    prob: float
    edge_distance: int  # tokens to the nearest window edge (higher = more context)


def merge_windows(windows: Sequence[Sequence[TokenPrediction]]) -> list[TokenPrediction]:
    """Combine overlapping windows: per character offset keep the most-centred prediction."""
    best: dict[Offset, TokenPrediction] = {}
    for window in windows:
        for tp in window:
            cur = best.get(tp.offset)
            if cur is None or tp.edge_distance > cur.edge_distance:
                best[tp.offset] = tp
    return [best[o] for o in sorted(best)]


class TokenClassifierRunner:
    """Batched, windowed inference for a Hugging Face token-classification model."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        device: torch.device,
        max_length: int = 512,
        stride: int = 64,
        batch_size: int = 32,
        source: str = "transformer",
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.max_length = max_length
        self.stride = stride
        self.batch_size = batch_size
        self.source = source

    @torch.inference_mode()
    def predict(self, texts: Sequence[str]) -> list[list[Span]]:
        enc = self.tokenizer(
            list(texts),
            truncation=True,
            max_length=self.max_length,
            stride=self.stride,
            return_overflowing_tokens=True,
            return_offsets_mapping=True,
        )
        owners: list[int] = list(enc["overflow_to_sample_mapping"])
        per_doc: list[list[list[TokenPrediction]]] = [[] for _ in texts]
        n = len(owners)
        self.model.eval()
        for b in range(0, n, self.batch_size):
            idx = list(range(b, min(n, b + self.batch_size)))
            batch = self.tokenizer.pad(
                {"input_ids": [enc["input_ids"][i] for i in idx],
                 "attention_mask": [enc["attention_mask"][i] for i in idx]},
                return_tensors="pt",
            )  # fmt: skip
            batch = {k: v.to(self.device) for k, v in batch.items()}
            # fp32 inference: under bf16, batch packing changed predictions with document order
            # and batch size (review M4-2: 2 dev docs differ); fp32 gave 0 differences.
            logits = self.model(**batch).logits
            probs = torch.softmax(logits.float(), dim=-1)
            conf, label_ids = probs.max(dim=-1)
            for row, i in enumerate(idx):
                doc = owners[i]
                offsets = clean_offsets(texts[doc], [tuple(o) for o in enc["offset_mapping"][i]])
                length = len(offsets)
                window = [
                    TokenPrediction(
                        offset=off,
                        label_id=int(label_ids[row, t]),
                        prob=float(conf[row, t]),
                        edge_distance=min(t, length - 1 - t),
                    )
                    for t, off in enumerate(offsets)
                    if off[0] != off[1]
                ]
                per_doc[doc].append(window)
        out = []
        for text, windows in zip(texts, per_doc, strict=True):
            merged = merge_windows(windows)
            out.append(
                labels_to_spans(
                    [m.offset for m in merged],
                    [m.label_id for m in merged],
                    [m.prob for m in merged],
                    source=self.source,
                    text=text,
                )
            )
        return out


__all__ = ["IGNORE", "TokenClassifierRunner", "TokenPrediction", "merge_windows"]
