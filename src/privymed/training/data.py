"""Encode documents into model inputs with aligned subword labels.

Usage (dataset statistics for model and window-size decisions; train/dev only)::

    uv run python -m privymed.training.data --tokenizers distilbert-base-cased roberta-base
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from privymed.config import find_repo_root
from privymed.io import read_documents
from privymed.schema import Document
from privymed.training.alignment import AlignmentStats, clean_offsets, spans_to_labels

DEV_SPLITS = ("train", "dev")


@dataclass
class Encoded:
    """One model window: token ids, attention mask, labels and character offsets."""

    doc_id: str
    input_ids: list[int]
    attention_mask: list[int]
    labels: list[int]
    offsets: list[tuple[int, int]]


@dataclass
class EncodeReport:
    documents: int = 0
    windows: int = 0
    stats: AlignmentStats = field(default_factory=AlignmentStats)
    tokens_per_doc: list[int] = field(default_factory=list)


def encode_documents(
    tokenizer: Any, docs: Sequence[Document], max_length: int = 512, stride: int = 64
) -> tuple[list[Encoded], EncodeReport]:
    """Tokenise documents, splitting long ones into overlapping windows.

    Overlapping windows (``stride`` tokens shared) make sure every token is seen with
    some context on both sides; at inference the overlapping predictions are merged.
    """
    out: list[Encoded] = []
    report = EncodeReport()
    agg = [0, 0, 0, 0]
    for doc in docs:
        enc = tokenizer(
            doc.text,
            truncation=True,
            max_length=max_length,
            stride=stride,
            return_overflowing_tokens=True,
            return_offsets_mapping=True,
        )
        report.documents += 1
        n_tokens = 0
        for w in range(len(enc["input_ids"])):
            offsets = clean_offsets(doc.text, [tuple(o) for o in enc["offset_mapping"][w]])
            labels, st = spans_to_labels(offsets, doc.spans)
            agg[0] += st.tokens
            agg[1] += st.entity_tokens
            agg[2] += st.straddling
            n_tokens = max(n_tokens, offsets[-2][1] if len(offsets) > 1 else 0)
            out.append(
                Encoded(
                    doc_id=doc.doc_id,
                    input_ids=list(enc["input_ids"][w]),
                    attention_mask=list(enc["attention_mask"][w]),
                    labels=labels,
                    offsets=offsets,
                )
            )
            report.windows += 1
        full = tokenizer(doc.text, add_special_tokens=False, return_offsets_mapping=True)
        full_offsets = clean_offsets(doc.text, [tuple(o) for o in full["offset_mapping"]])
        _, full_stats = spans_to_labels(full_offsets, doc.spans)
        agg[3] += full_stats.unlabelled_spans
        report.tokens_per_doc.append(len(full["input_ids"]))
    report.stats = AlignmentStats(
        tokens=agg[0], entity_tokens=agg[1], straddling=agg[2], unlabelled_spans=agg[3]
    )
    return out, report


def _max_len(tokenizer: Any) -> int:
    """Model input limit; some tokenizers report a huge sentinel when it is unset."""
    limit = int(tokenizer.model_max_length)
    return limit if limit < 100_000 else 512


def token_length_stats(tokenizer_names: Sequence[str], root: Path) -> dict[str, object]:
    """Subword length distribution and alignment quality per tokenizer on train/dev."""
    from transformers import AutoTokenizer

    docs = {s: read_documents(root / f"data/synthetic/v1/{s}.jsonl") for s in DEV_SPLITS}
    result: dict[str, object] = {"splits": list(DEV_SPLITS), "tokenizers": {}}
    for name in tokenizer_names:
        tok = AutoTokenizer.from_pretrained(name, use_fast=True)
        per_split = {}
        for split, split_docs in docs.items():
            _, rep = encode_documents(
                tok,
                split_docs,
                max_length=tok.model_max_length if tok.model_max_length < 10**6 else 512,
            )
            lengths = np.array(rep.tokens_per_doc)
            per_split[split] = {
                "documents": rep.documents,
                "tokens_mean": round(float(lengths.mean()), 1),
                "tokens_p50": int(np.percentile(lengths, 50)),
                "tokens_p95": int(np.percentile(lengths, 95)),
                "tokens_p99": int(np.percentile(lengths, 99)),
                "tokens_max": int(lengths.max()),
                "docs_over_256": int((lengths > 254).sum()),
                "docs_over_512": int((lengths > 510).sum()),
                "straddling_tokens": rep.stats.straddling,
                "unlabelled_spans": rep.stats.unlabelled_spans,
                "entity_token_share": round(rep.stats.entity_tokens / rep.stats.tokens, 4),
            }
        result["tokenizers"][name] = per_split  # type: ignore[index]
    return result


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Subword statistics on train/dev.")
    parser.add_argument("--tokenizers", nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/data/v1_token_stats.json"))
    args = parser.parse_args(argv)
    root = find_repo_root()
    stats = token_length_stats(args.tokenizers, root)
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name, per in stats["tokenizers"].items():  # type: ignore[attr-defined]
        for split, s in per.items():
            print(
                f"{name:<28} {split:<5} mean={s['tokens_mean']:>6} p95={s['tokens_p95']:>4} "
                f"max={s['tokens_max']:>4} >512={s['docs_over_512']:>3} "
                f"straddle={s['straddling_tokens']} unlabelled={s['unlabelled_spans']}"
            )


if __name__ == "__main__":
    main()
