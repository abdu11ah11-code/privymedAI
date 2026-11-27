"""Span-level precision / recall / F1 under four matching modes, plus leak rate.

Evaluation protocol (documented in docs/EVALUATION.md):

Matching modes
    ``strict``    TP iff a prediction has exactly the gold boundaries AND label.
    ``boundary``  TP iff exact boundaries; label ignored.
    ``partial``   TP iff the prediction overlaps the gold span AND has its label.
    ``overlap``   TP iff the prediction overlaps the gold span; label ignored.
                  ("Would redacting the prediction have hidden this entity?")

Rules common to all modes
    * Matching is one-to-one: a prediction matches at most one gold span and
      vice versa. The matching maximises the number of matched pairs, then the
      total character overlap (Hungarian algorithm; deterministic).
    * Duplicate predictions (same start, end, label) are collapsed first;
      they are neither rewarded nor double-penalised.
    * Unmatched predictions are false positives, attributed to the predicted
      label; unmatched gold spans are false negatives, attributed to the gold
      label. A TP is attributed to the gold label.
    * Micro scores pool counts over all labels; macro scores average per-label
      F1 over labels that occur in gold.

Leak rate
    Share of gold PII characters not covered by any prediction (any label).
    This is the most direct privacy measure: it ignores labels and boundaries.

Confidence intervals
    Percentile bootstrap over documents (resample documents with replacement).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from privymed.schema import Document, EntityType, Span

Mode = Literal["strict", "boundary", "partial", "overlap"]
MODES: tuple[Mode, ...] = ("strict", "boundary", "partial", "overlap")
_LABELS = tuple(EntityType)


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: Counts) -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def _dedupe(preds: Iterable[Span]) -> list[Span]:
    seen: dict[tuple[int, int, EntityType], Span] = {}
    for p in preds:
        seen.setdefault(p.key, p)
    return sorted(seen.values(), key=lambda s: s.key)


def _overlap(a: Span, b: Span) -> int:
    return max(0, min(a.end, b.end) - max(a.start, b.start))


def _is_candidate(mode: Mode, g: Span, p: Span) -> bool:
    match mode:
        case "strict":
            return g.range == p.range and g.label is p.label
        case "boundary":
            return g.range == p.range
        case "partial":
            return _overlap(g, p) > 0 and g.label is p.label
        case "overlap":
            return _overlap(g, p) > 0


def _max_matching(
    candidates: Sequence[tuple[int, int, int]], n_gold: int, n_pred: int
) -> list[tuple[int, int]]:
    """Maximum-cardinality one-to-one matching; among those, maximum total overlap.

    Greedy "largest overlap first" is not maximum-cardinality when predictions
    overlap several gold spans (review finding M3-4: gold [0,10) [10,20), predictions
    [2,18) [0,3) -> greedy 1 TP, optimal 2 TP). Solved exactly with the Hungarian
    algorithm; weight = BIG + overlap so cardinality dominates, overlap breaks ties.
    The result is deterministic for a given input.
    """
    if not candidates:
        return []
    gold_degree = Counter(gi for _, gi, _ in candidates)
    pred_degree = Counter(pi for _, _, pi in candidates)
    if max(gold_degree.values()) == 1 and max(pred_degree.values()) == 1:
        # Every candidate pair is conflict-free (always true in strict/boundary mode).
        return sorted((gi, pi) for _, gi, pi in candidates)
    from scipy.optimize import linear_sum_assignment

    big = 1 + sum(ov for ov, _, _ in candidates)
    weight = np.zeros((n_gold, n_pred))
    for ov, gi, pi in candidates:
        weight[gi, pi] = big + ov
    rows, cols = linear_sum_assignment(weight, maximize=True)
    return sorted((int(r), int(c)) for r, c in zip(rows, cols, strict=True) if weight[r, c] > 0)


def match_document(
    gold: Sequence[Span], preds: Sequence[Span], mode: Mode
) -> tuple[dict[EntityType, Counts], list[tuple[int, int]]]:
    """Match one document. Returns per-label counts and matched (gold_idx, pred_idx) pairs."""
    gold = sorted(gold, key=lambda s: s.key)
    preds = _dedupe(preds)
    candidates = [
        (_overlap(g, p), gi, pi)
        for gi, g in enumerate(gold)
        for pi, p in enumerate(preds)
        if _is_candidate(mode, g, p)
    ]
    pairs = _max_matching(candidates, len(gold), len(preds))
    used_g = {gi for gi, _ in pairs}
    used_p = {pi for _, pi in pairs}
    counts = {label: Counts() for label in _LABELS}
    for gi, _ in pairs:
        counts[gold[gi].label].tp += 1
    for gi, g in enumerate(gold):
        if gi not in used_g:
            counts[g.label].fn += 1
    for pi, p in enumerate(preds):
        if pi not in used_p:
            counts[p.label].fp += 1
    return counts, sorted(pairs)


def leak_chars(gold: Sequence[Span], preds: Sequence[Span]) -> tuple[int, int]:
    """(gold PII characters not covered by any prediction, total gold PII characters)."""
    covered: set[int] = set()
    for p in preds:
        covered.update(range(p.start, p.end))
    total = sum(g.length for g in gold)
    leaked = sum(1 for g in gold for i in range(g.start, g.end) if i not in covered)
    return leaked, total


def leak_rate(gold_docs: Sequence[Document], predictions: Mapping[str, Sequence[Span]]) -> float:
    leaked = total = 0
    for doc in gold_docs:
        lk, tot = leak_chars(doc.spans, predictions.get(doc.doc_id, ()))
        leaked += lk
        total += tot
    return leaked / total if total else 0.0


@dataclass
class EvalResult:
    """Aggregated evaluation of one system on one document set."""

    n_docs: int
    per_label: dict[Mode, dict[EntityType, Counts]]
    leaked_chars: int
    gold_chars: int
    # Per-document micro counts [n_docs, 3] per mode (tp, fp, fn) — used for bootstrap CIs.
    doc_counts: dict[Mode, np.ndarray] = field(repr=False)
    doc_leaks: np.ndarray = field(repr=False)  # [n_docs, 2] (leaked, total)

    def micro(self, mode: Mode) -> Counts:
        total = Counts()
        for c in self.per_label[mode].values():
            total.add(c)
        return total

    def macro_f1(self, mode: Mode) -> float:
        present = [c for c in self.per_label[mode].values() if c.tp + c.fn > 0]
        return float(np.mean([c.f1 for c in present])) if present else 0.0

    @property
    def leak_rate(self) -> float:
        return self.leaked_chars / self.gold_chars if self.gold_chars else 0.0

    def bootstrap(
        self, mode: Mode, n_resamples: int = 1000, seed: int = 0, alpha: float = 0.05
    ) -> dict[str, tuple[float, float]]:
        """Percentile CIs for micro precision/recall/F1 by resampling documents."""
        rng = np.random.default_rng(seed)
        counts = self.doc_counts[mode]
        idx = rng.integers(0, self.n_docs, size=(n_resamples, self.n_docs))
        sums = counts[idx].sum(axis=1)  # [n_resamples, 3]
        tp, fp, fn = sums[:, 0], sums[:, 1], sums[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            p = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
            r = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
            f = np.where(p + r > 0, 2 * p * r / (p + r), 0.0)
        leaks = self.doc_leaks[idx].sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            lr = np.where(leaks[:, 1] > 0, leaks[:, 0] / leaks[:, 1], 0.0)
        lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)

        def ci(v: np.ndarray) -> tuple[float, float]:
            return (round(float(np.percentile(v, lo)), 4), round(float(np.percentile(v, hi)), 4))

        return {"precision": ci(p), "recall": ci(r), "f1": ci(f), "leak_rate": ci(lr)}

    def summary(self, bootstrap: bool = True) -> dict[str, object]:
        out: dict[str, object] = {"n_docs": self.n_docs, "leak_rate": round(self.leak_rate, 4)}
        for mode in MODES:
            block: dict[str, object] = {
                "micro": self.micro(mode).as_dict(),
                "macro_f1": round(self.macro_f1(mode), 4),
                "per_label": {
                    label.value: c.as_dict() for label, c in self.per_label[mode].items()
                },
            }
            if bootstrap:
                block["ci95"] = self.bootstrap(mode)
            out[mode] = block
        return out


def evaluate(
    gold_docs: Sequence[Document], predictions: Mapping[str, Sequence[Span]]
) -> EvalResult:
    """Evaluate predictions (keyed by ``doc_id``) against gold documents.

    Documents missing from ``predictions`` count as "predicted nothing".
    Predictions for unknown ``doc_id``s raise, since they indicate a pipeline bug.
    """
    unknown = set(predictions) - {d.doc_id for d in gold_docs}
    if unknown:
        raise ValueError(f"predictions for {len(unknown)} unknown doc_id(s)")
    per_label: dict[Mode, dict[EntityType, Counts]] = {
        m: {label: Counts() for label in _LABELS} for m in MODES
    }
    doc_counts = {m: np.zeros((len(gold_docs), 3), dtype=np.int64) for m in MODES}
    doc_leaks = np.zeros((len(gold_docs), 2), dtype=np.int64)
    for i, doc in enumerate(gold_docs):
        preds = predictions.get(doc.doc_id, ())
        for mode in MODES:
            counts, _ = match_document(doc.spans, preds, mode)
            for label, c in counts.items():
                per_label[mode][label].add(c)
                doc_counts[mode][i] += (c.tp, c.fp, c.fn)
        doc_leaks[i] = leak_chars(doc.spans, preds)
    return EvalResult(
        n_docs=len(gold_docs),
        per_label=per_label,
        leaked_chars=int(doc_leaks[:, 0].sum()),
        gold_chars=int(doc_leaks[:, 1].sum()),
        doc_counts=doc_counts,
        doc_leaks=doc_leaks,
    )
