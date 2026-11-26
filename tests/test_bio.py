from __future__ import annotations

import pytest

from privymed.bio import AlignmentError, bio_to_spans, spans_to_bio, tokenize
from privymed.schema import EntityType, Span


def _s(a: int, b: int, label: EntityType) -> Span:
    return Span(start=a, end=b, label=label)


def test_tokenize_offsets() -> None:
    text = "Dr. Ali, MRN-12"
    assert [text[a:b] for a, b in tokenize(text)] == ["Dr", ".", "Ali", ",", "MRN", "-", "12"]


def test_multi_token_span_gets_b_then_i() -> None:
    text = "Patient Ayesha Khan, ph 0300-1234567."
    spans = [_s(8, 19, EntityType.PATIENT), _s(24, 36, EntityType.PHONE)]
    tokens = tokenize(text)
    tags = spans_to_bio(tokens, spans)
    assert tags == ["O", "B-PATIENT", "I-PATIENT", "O", "O", "B-PHONE", "I-PHONE", "I-PHONE", "O"]
    assert [s.key for s in bio_to_spans(tokens, tags)] == [s.key for s in spans]


def test_adjacent_same_type_spans_stay_separate() -> None:
    text = "A,B"
    spans = [_s(0, 1, EntityType.ID), _s(2, 3, EntityType.ID)]
    tags = spans_to_bio(tokenize(text), spans)
    assert tags == ["B-ID", "O", "B-ID"]


def test_touching_spans_without_separator() -> None:
    # "Ali" then "Khan" as two spans with a space: two B tags
    text = "Ali Khan"
    spans = [_s(0, 3, EntityType.PATIENT), _s(4, 8, EntityType.PATIENT)]
    tags = spans_to_bio(tokenize(text), spans)
    assert tags == ["B-PATIENT", "B-PATIENT"]
    assert len(bio_to_spans(tokenize(text), tags)) == 2


def test_mid_token_boundary_raises() -> None:
    text = "MRN12345"  # one token; span covers only the digits
    with pytest.raises(AlignmentError):
        spans_to_bio(tokenize(text), [_s(3, 8, EntityType.ID)])


def test_stray_inside_tag_starts_new_span() -> None:
    tokens = tokenize("a b c")
    spans = bio_to_spans(tokens, ["O", "I-DATE", "I-DATE"])
    assert [s.range for s in spans] == [(2, 5)]


def test_label_change_inside_run_splits_spans() -> None:
    tokens = tokenize("a b")
    spans = bio_to_spans(tokens, ["B-DATE", "I-ID"])
    assert [(s.range, s.label) for s in spans] == [
        ((0, 1), EntityType.DATE),
        ((2, 3), EntityType.ID),
    ]


def test_invalid_tag_raises() -> None:
    with pytest.raises(ValueError):
        bio_to_spans(tokenize("a"), ["X-DATE"])
