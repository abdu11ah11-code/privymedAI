"""Evaluator tests: hand-computed cases for every mode, edge cases, and a seqeval cross-check."""

from __future__ import annotations

import random

import pytest
from seqeval.metrics import f1_score, precision_score, recall_score
from seqeval.scheme import IOB2

from privymed.bio import spans_to_bio, tokenize
from privymed.data_generation.engine import generate_document
from privymed.data_generation.entities import EntityFactory
from privymed.data_generation.families import FAMILIES
from privymed.data_generation.noise import CLEAN
from privymed.evaluation import Mode, evaluate, match_document
from privymed.evaluation.metrics import leak_chars
from privymed.schema import Document, EntityType, Span

P, D, PH, ST, ID = (
    EntityType.PATIENT,
    EntityType.DATE,
    EntityType.PHONE,
    EntityType.STAFF,
    EntityType.ID,
)


def s(a: int, b: int, label: EntityType, source: str = "sys") -> Span:
    return Span(start=a, end=b, label=label, source=source)


# Gold: PATIENT [0,11)  DATE [20,30)  PHONE [40,52)
GOLD = [s(0, 11, P, "gold"), s(20, 30, D, "gold"), s(40, 52, PH, "gold")]
PREDS = [
    s(0, 11, P),  # exact                      -> TP in every mode
    s(0, 11, P),  # duplicate of the above     -> collapsed, not counted twice
    s(20, 28, D),  # right label, short by 2    -> TP only in partial/overlap
    s(40, 52, ST),  # right boundaries, wrong label -> TP only in boundary/overlap
    s(60, 65, ID),  # spurious                  -> FP in every mode
]

# (tp, fp, fn) worked out by hand — see comments above.
EXPECTED = {
    "strict": (1, 3, 2),  # FP: DATE-short, STAFF, ID   FN: DATE, PHONE
    "boundary": (2, 2, 1),  # TP: PATIENT, PHONE(=STAFF range)  FP: DATE-short, ID  FN: DATE
    "partial": (2, 2, 1),  # TP: PATIENT, DATE  FP: STAFF, ID  FN: PHONE
    "overlap": (3, 1, 0),  # everything overlaps except the spurious ID
}


@pytest.mark.parametrize("mode", list(EXPECTED))
def test_hand_computed_counts(mode: str) -> None:
    counts, _ = match_document(GOLD, PREDS, mode)  # type: ignore[arg-type]
    tp = sum(c.tp for c in counts.values())
    fp = sum(c.fp for c in counts.values())
    fn = sum(c.fn for c in counts.values())
    assert (tp, fp, fn) == EXPECTED[mode]


def test_hand_computed_strict_scores_and_attribution() -> None:
    doc = Document(doc_id="d", text="x" * 70, spans=tuple(GOLD))
    res = evaluate([doc], {"d": PREDS})
    micro = res.micro("strict")
    assert (micro.precision, round(micro.recall, 4), round(micro.f1, 4)) == (0.25, 0.3333, 0.2857)
    per = res.per_label["strict"]
    assert (per[ST].fp, per[PH].fn, per[ID].fp, per[D].fp, per[D].fn) == (1, 1, 1, 1, 1)
    # boundary-mode TP for the wrong-label phone is credited to the GOLD label
    assert res.per_label["boundary"][PH].tp == 1
    assert res.per_label["boundary"][ST].tp == 0


def test_leak_rate_hand_computed() -> None:
    # gold chars = 11 + 10 + 12 = 33; only DATE chars 28,29 are uncovered
    assert leak_chars(GOLD, PREDS) == (2, 33)


def test_one_prediction_cannot_match_two_gold_spans() -> None:
    gold = [s(0, 5, P, "gold"), s(6, 10, P, "gold")]
    counts, pairs = match_document(gold, [s(0, 10, P)], "overlap")
    assert pairs == [(0, 0)]  # matched to the larger overlap (5 chars vs 4)
    assert (counts[P].tp, counts[P].fn, counts[P].fp) == (1, 1, 0)


def test_matching_is_maximum_cardinality_reviewer_counterexample() -> None:
    """Review M3-4: greedy-by-overlap gave 1 TP here; the optimal matching gives 2."""
    gold = [s(0, 10, P, "gold"), s(10, 20, P, "gold")]
    preds = [s(2, 18, P), s(0, 3, P)]
    modes: tuple[Mode, ...] = ("partial", "overlap")
    for mode in modes:
        counts, pairs = match_document(gold, preds, mode)
        assert (counts[P].tp, counts[P].fp, counts[P].fn) == (2, 0, 0), mode
        assert len(pairs) == 2


def _brute_force_max_tp(gold: list[Span], preds: list[Span], mode: Mode) -> int:
    from itertools import permutations

    from privymed.evaluation.metrics import _dedupe, _is_candidate

    preds = _dedupe(preds)
    best = 0
    # try every injective assignment of preds (plus "unmatched") to gold
    slots = list(range(len(preds))) + [-1] * len(gold)
    for perm in set(permutations(slots, len(gold))):
        used = [p for p in perm if p >= 0]
        if len(used) != len(set(used)):
            continue
        tp = sum(
            1
            for g, p in zip(gold, perm, strict=True)
            if p >= 0 and _is_candidate(mode, g, preds[p])
        )
        best = max(best, tp)
    return best


@pytest.mark.parametrize("mode", ["strict", "boundary", "partial", "overlap"])
def test_matching_tp_equals_brute_force_optimum(mode: Mode) -> None:
    rng = random.Random(7)
    labels = [P, D]
    for _ in range(300):
        gold, pos = [], 0
        for _ in range(rng.randint(0, 3)):  # non-overlapping gold
            a = pos + rng.randint(0, 3)
            b = a + rng.randint(1, 6)
            gold.append(s(a, b, rng.choice(labels), "gold"))
            pos = b
        preds = []
        for _ in range(rng.randint(0, 4)):  # predictions may overlap anything
            a = rng.randint(0, max(1, pos))
            preds.append(s(a, a + rng.randint(1, 8), rng.choice(labels)))
        counts, _ = match_document(gold, preds, mode)
        assert sum(c.tp for c in counts.values()) == _brute_force_max_tp(gold, preds, mode)


def test_two_predictions_cannot_both_match_one_gold_span() -> None:
    counts, _ = match_document([s(0, 10, P, "gold")], [s(0, 5, P), s(5, 10, P)], "partial")
    assert (counts[P].tp, counts[P].fp) == (1, 1)


def test_missing_document_counts_as_no_predictions() -> None:
    doc = Document(doc_id="d", text="x" * 20, spans=(s(0, 5, P, "gold"),))
    res = evaluate([doc], {})
    assert res.micro("strict").fn == 1 and res.leak_rate == 1.0


def test_unknown_doc_id_raises() -> None:
    with pytest.raises(ValueError, match="unknown"):
        evaluate([], {"ghost": []})


def test_entity_free_document_only_produces_false_positives() -> None:
    doc = Document(doc_id="d", text="x" * 20)
    res = evaluate([doc], {"d": [s(0, 3, ID)]})
    assert res.micro("overlap").fp == 1 and res.gold_chars == 0 and res.leak_rate == 0.0


def test_macro_ignores_labels_absent_from_gold() -> None:
    doc = Document(doc_id="d", text="x" * 30, spans=(s(0, 5, P, "gold"), s(10, 15, D, "gold")))
    res = evaluate([doc], {"d": [s(0, 5, P)]})  # PATIENT F1 = 1, DATE F1 = 0
    assert res.macro_f1("strict") == 0.5


def test_bootstrap_is_deterministic_and_brackets_point_estimate() -> None:
    rng = random.Random(0)
    docs, preds = [], {}
    for i in range(60):
        gold = (s(0, 5, P, "gold"), s(10, 15, D, "gold"))
        docs.append(Document(doc_id=str(i), text="x" * 20, spans=gold))
        preds[str(i)] = [g for g in gold if rng.random() < 0.7]
    res = evaluate(docs, preds)
    ci = res.bootstrap("strict", seed=1)
    assert ci == res.bootstrap("strict", seed=1)
    lo, hi = ci["recall"]
    assert lo <= res.micro("strict").recall <= hi and lo < hi


def test_perfect_predictions_score_one_with_degenerate_ci() -> None:
    docs = [Document(doc_id="d", text="x" * 20, spans=(s(0, 5, P, "gold"),))]
    res = evaluate(docs, {"d": [s(0, 5, P)]})
    assert res.micro("strict").f1 == 1.0
    assert res.bootstrap("strict")["f1"] == (1.0, 1.0)


# ------------------------------------------------------------------ seqeval cross-check
def _perturbed_predictions(doc: Document, rng: random.Random) -> list[Span]:
    """Token-aligned, non-overlapping predictions with realistic error types."""
    tokens = tokenize(doc.text)
    labels = list(EntityType)
    preds: list[Span] = []
    for g in doc.spans:
        r = rng.random()
        if r < 0.15:
            continue  # miss
        if r < 0.30:
            preds.append(Span(start=g.start, end=g.end, label=rng.choice(labels)))  # relabel
            continue
        if r < 0.45:
            inside = [t for t in tokens if g.start <= t[0] and t[1] <= g.end]
            if len(inside) > 1:  # shrink to all but the last token
                preds.append(Span(start=inside[0][0], end=inside[-2][1], label=g.label))
                continue
        preds.append(Span(start=g.start, end=g.end, label=g.label))
    covered = {i for p in preds for i in range(p.start, p.end)} | {
        i for g in doc.spans for i in range(g.start, g.end)
    }
    for t in tokens:  # spurious single-token predictions on free text
        if rng.random() < 0.03 and not covered & set(range(t[0], t[1])):
            preds.append(Span(start=t[0], end=t[1], label=rng.choice(labels)))
            covered |= set(range(t[0], t[1]))
    return preds


def test_strict_mode_matches_seqeval() -> None:
    """Our strict micro P/R/F1 must equal seqeval's (IOB2, strict) on token-aligned predictions."""
    factory = EntityFactory(0)
    rng = random.Random(42)
    docs = [
        generate_document(fam, factory, 3, i, noise=CLEAN) for fam in FAMILIES for i in range(15)
    ]
    preds = {d.doc_id: _perturbed_predictions(d, rng) for d in docs}
    res = evaluate(docs, preds)
    y_true, y_pred = [], []
    for d in docs:
        tokens = tokenize(d.text)
        y_true.append(spans_to_bio(tokens, d.spans))
        y_pred.append(spans_to_bio(tokens, preds[d.doc_id]))
    kw = {"mode": "strict", "scheme": IOB2}
    micro = res.micro("strict")
    assert micro.tp > 500 and micro.fp > 100 and micro.fn > 100  # a non-trivial test
    assert micro.precision == pytest.approx(precision_score(y_true, y_pred, **kw))
    assert micro.recall == pytest.approx(recall_score(y_true, y_pred, **kw))
    assert micro.f1 == pytest.approx(f1_score(y_true, y_pred, **kw))
