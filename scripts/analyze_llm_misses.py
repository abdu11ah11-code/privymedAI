"""Analyse missed gold entities of the LLM baseline from its saved raw outputs (dev only).

Usage: uv run python scripts/analyze_llm_misses.py [--label PATIENT] [--show 15]

Reads reports/eval/raw/llm_v1_dev.jsonl (written by privymed-eval) and the dev split,
re-maps each raw response exactly as the detector does, and groups gold spans of one type
that no prediction overlaps, by the gold span's format tag and the words just before it.
Never touches the test split (CLAUDE.md rule 3).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from privymed.config import find_repo_root
from privymed.io import read_documents
from privymed.llm.mapping import map_mentions, parse_response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="PATIENT")
    parser.add_argument("--show", type=int, default=15)
    parser.add_argument("--raw", default="reports/eval/raw/llm_v1_dev.jsonl")
    args = parser.parse_args()
    root = find_repo_root()
    docs = {d.doc_id: d for d in read_documents(root / "data/synthetic/v1/dev.jsonl")}
    raw = [json.loads(line) for line in (root / args.raw).read_text(encoding="utf-8").splitlines()]
    missed_fmt: Counter[str] = Counter()
    missed_ctx: Counter[str] = Counter()
    wrong_label: Counter[str] = Counter()
    total = shown = 0
    for row in raw:
        doc = docs[row["doc_id"]]
        mentions = parse_response(row["response"]) or []
        preds, _ = map_mentions(doc.text, mentions)
        for g in (s for s in doc.spans if s.label.value == args.label):
            total += 1
            over = [p for p in preds if p.overlaps(g)]
            if over:
                if all(p.label is not g.label for p in over):
                    wrong_label[over[0].label.value] += 1
                continue
            fmt = (g.fmt or "none").split("+")[0]
            ctx = " ".join(doc.text[max(0, g.start - 25) : g.start].split()[-2:])
            missed_fmt[fmt] += 1
            missed_ctx[ctx] += 1
            if shown < args.show:
                print(f"MISSED {row['doc_id']}: {doc.span_text(g)!r} fmt={g.fmt} after {ctx!r}")
                shown += 1
    missed = sum(missed_fmt.values())
    print(f"\n{args.label}: {missed} of {total} gold spans have no overlapping prediction")
    print("by format:", missed_fmt.most_common(8))
    print("by preceding words:", missed_ctx.most_common(8))
    print("found but labelled as another type:", wrong_label.most_common())


if __name__ == "__main__":
    main()
