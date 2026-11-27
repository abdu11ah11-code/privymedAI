"""Subword alignment tests with hand-written offset mappings (no tokenizer needed)."""

from __future__ import annotations

import pytest

from privymed.schema import EntityType, Span
from privymed.training.alignment import (
    IGNORE,
    LABEL2ID,
    LABELS,
    labels_to_spans,
    spans_to_labels,
)

P, PH = EntityType.PATIENT, EntityType.PHONE
TEXT = "Pt Siddiqui ph 0300-1234567"
#       0123456789012345678901234567
# subwords: [CLS] Pt Sid ##di ##qui ph 03 ##00 - 12 ##34 ##567 [SEP]
OFFSETS = [
    (0, 0), (0, 2), (3, 6), (6, 8), (8, 11), (12, 14),
    (15, 17), (17, 19), (19, 20), (20, 22), (22, 24), (24, 27), (0, 0),
]  # fmt: skip
GOLD = [Span(start=3, end=11, label=P), Span(start=15, end=27, label=PH)]


def lab(name: str) -> int:
    return LABEL2ID[name]


def test_label_set_is_bio_over_nine_types() -> None:
    assert len(LABELS) == 1 + 2 * 9 and LABELS[0] == "O"


def test_all_subwords_labelled_b_then_i_and_specials_ignored() -> None:
    labels, stats = spans_to_labels(OFFSETS, GOLD)
    assert labels == [
        IGNORE, lab("O"),
        lab("B-PATIENT"), lab("I-PATIENT"), lab("I-PATIENT"),
        lab("O"),
        lab("B-PHONE"), lab("I-PHONE"), lab("I-PHONE"),
        lab("I-PHONE"), lab("I-PHONE"), lab("I-PHONE"),
        IGNORE,
    ]  # fmt: skip
    assert stats.straddling == 0 and stats.unlabelled_spans == 0
    assert stats.tokens == 11 and stats.entity_tokens == 9


def test_round_trip_recovers_exact_character_spans() -> None:
    labels, _ = spans_to_labels(OFFSETS, GOLD)
    assert [s.key for s in labels_to_spans(OFFSETS, labels)] == [g.key for g in GOLD]


def test_adjacent_same_type_spans_stay_separate() -> None:
    offsets = [(0, 3), (3, 4), (4, 7)]  # "Ali" "," "Bob"
    gold = [Span(start=0, end=3, label=P), Span(start=4, end=7, label=P)]
    labels, _ = spans_to_labels(offsets, gold)
    assert [s.range for s in labels_to_spans(offsets, labels)] == [(0, 3), (4, 7)]


def test_touching_spans_without_separator_split_on_b_tag() -> None:
    offsets = [(0, 3), (3, 6)]
    gold = [Span(start=0, end=3, label=EntityType.ID), Span(start=3, end=6, label=EntityType.ID)]
    labels, _ = spans_to_labels(offsets, gold)
    assert labels == [lab("B-ID"), lab("B-ID")]
    assert len(labels_to_spans(offsets, labels)) == 2


def test_straddling_token_is_counted() -> None:
    offsets = [(0, 5)]  # one subword "MRN12" but the span is only "12"
    _, stats = spans_to_labels(offsets, [Span(start=3, end=5, label=EntityType.ID)])
    assert stats.straddling == 1 and stats.unlabelled_spans == 1


def test_lenient_decoding_and_label_switch() -> None:
    offsets = [(0, 2), (3, 5), (6, 8)]
    spans = labels_to_spans(offsets, [lab("I-DATE"), lab("I-DATE"), lab("I-ID")])
    assert [(s.range, s.label) for s in spans] == [
        ((0, 5), EntityType.DATE),
        ((6, 8), EntityType.ID),
    ]


def test_span_score_is_mean_subword_probability() -> None:
    offsets = [(0, 2), (2, 4)]
    spans = labels_to_spans(offsets, [lab("B-ID"), lab("I-ID")], scores=[0.9, 0.5])
    assert spans[0].score == 0.7 and spans[0].source == "transformer"


def test_clean_offsets_trims_sentencepiece_leading_space() -> None:
    from privymed.training.alignment import clean_offsets

    text = "Pt Khan"
    # DeBERTa-v3 style: "▁Khan" reported as (2, 7) including the space at index 2
    assert clean_offsets(text, [(0, 0), (0, 2), (2, 7), (0, 0)]) == [(0, 0), (0, 2), (3, 7), (0, 0)]
    assert clean_offsets("a  b", [(1, 3)]) == [(0, 0)]  # whitespace-only token -> ignored


@pytest.mark.slow
@pytest.mark.parametrize("name", ["distilbert-base-cased", "microsoft/deberta-v3-base"])
def test_real_tokenizers_align_without_straddling(name: str) -> None:
    """Integration: real offset mappings must align perfectly on generated documents."""
    transformers = pytest.importorskip("transformers")
    from privymed.data_generation.engine import generate_document
    from privymed.data_generation.entities import EntityFactory
    from privymed.data_generation.families import FAMILIES
    from privymed.data_generation.noise import CLEAN
    from privymed.training.data import encode_documents

    try:
        tok = transformers.AutoTokenizer.from_pretrained(name)
    except OSError:
        pytest.skip(f"{name} not available offline")
    factory = EntityFactory(0)
    docs = [generate_document(f, factory, 9, i, noise=CLEAN) for f in FAMILIES for i in range(5)]
    encoded, report = encode_documents(tok, docs, max_length=128, stride=32)
    assert report.stats.straddling == 0 and report.stats.unlabelled_spans == 0
    assert report.windows > report.documents  # max_length=128 forces some windowing
    # round trip on every single-window document
    single = {e.doc_id for e in encoded}
    for doc in docs:
        windows = [e for e in encoded if e.doc_id == doc.doc_id]
        if len(windows) == 1 and doc.doc_id in single:
            spans = labels_to_spans(windows[0].offsets, windows[0].labels)
            assert [s.key for s in spans] == [g.key for g in doc.spans], doc.doc_id
