from __future__ import annotations

import pytest
from pydantic import ValidationError

from privymed.schema import Document, EntityType, Span, validate_spans_against_text

TEXT = "Patient Ayesha Khan seen by Dr. John Smith on 12/03/2024."
#        0123456789...
PATIENT = Span(start=8, end=19, label=EntityType.PATIENT)  # "Ayesha Khan"
STAFF = Span(start=28, end=42, label=EntityType.STAFF)  # "Dr. John Smith"
DATE = Span(start=46, end=56, label=EntityType.DATE)  # "12/03/2024"


def test_schema_has_exactly_nine_types() -> None:
    assert len(EntityType) == 9


def test_offsets_match_expected_surface_text() -> None:
    doc = Document(doc_id="d1", text=TEXT, spans=(PATIENT, STAFF, DATE))
    assert [doc.span_text(s) for s in doc.spans] == ["Ayesha Khan", "Dr. John Smith", "12/03/2024"]


def test_spans_are_sorted_on_construction() -> None:
    doc = Document(doc_id="d1", text=TEXT, spans=(DATE, PATIENT, STAFF))
    assert doc.spans == (PATIENT, STAFF, DATE)


@pytest.mark.parametrize(("start", "end"), [(5, 5), (6, 5), (-1, 3)])
def test_invalid_span_bounds_rejected(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        Span(start=start, end=end, label=EntityType.DATE)


def test_score_must_be_probability() -> None:
    with pytest.raises(ValidationError):
        Span(start=0, end=1, label=EntityType.ID, score=1.5)


def test_span_outside_text_rejected() -> None:
    with pytest.raises(ValidationError, match="exceeds text length"):
        Document(doc_id="d1", text="short", spans=(Span(start=0, end=99, label=EntityType.ID),))


def test_overlapping_gold_spans_rejected() -> None:
    bad = Span(start=15, end=30, label=EntityType.STAFF)
    with pytest.raises(ValidationError, match="overlapping"):
        Document(doc_id="d1", text=TEXT, spans=(PATIENT, bad))


def test_adjacent_spans_are_not_overlapping() -> None:
    a = Span(start=0, end=3, label=EntityType.ID)
    b = Span(start=3, end=6, label=EntityType.ID)
    assert not a.overlaps(b)
    Document(doc_id="d1", text="ABCDEF", spans=(a, b))


def test_whitespace_boundary_rejected() -> None:
    with pytest.raises(ValidationError, match="whitespace"):
        Document(doc_id="d1", text=TEXT, spans=(Span(start=7, end=19, label=EntityType.PATIENT),))


def test_unknown_label_rejected() -> None:
    with pytest.raises(ValidationError):
        Span.model_validate({"start": 0, "end": 1, "label": "OTHER_PII"})


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Span.model_validate({"start": 0, "end": 1, "label": "ID", "typo_field": 1})


def test_json_roundtrip() -> None:
    doc = Document(doc_id="d1", text=TEXT, spans=(PATIENT, STAFF), metadata={"family": "t01"})
    assert Document.model_validate_json(doc.model_dump_json()) == doc


def test_key_ignores_score_and_source() -> None:
    pred = Span(start=8, end=19, label=EntityType.PATIENT, score=0.7, source="bert")
    assert pred != PATIENT  # full equality includes score/source...
    assert pred.key == PATIENT.key  # ...so evaluators must compare keys
    assert pred.range == (8, 19)


def test_nested_gold_spans_rejected() -> None:
    outer = Span(start=0, end=10, label=EntityType.ADDRESS)
    inner = Span(start=2, end=3, label=EntityType.ID)
    with pytest.raises(ValidationError, match="overlapping"):
        Document(doc_id="d1", text="0123456789", spans=(outer, inner))


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("Ayesha ", 0, 7),  # trailing space
        ("   ", 0, 3),  # whitespace only
        ("Ayesha​", 0, 7),  # trailing zero-width space
        ("﻿Ayesha", 0, 7),  # leading BOM
    ],
)
def test_bad_boundary_characters_rejected(text: str, start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        Document(doc_id="d1", text=text, spans=(Span(start=start, end=end, label=EntityType.ID),))


@pytest.mark.parametrize("bad", [True, 1.0, "3"])
def test_span_offsets_are_strict_ints(bad: object) -> None:
    with pytest.raises(ValidationError):
        Span.model_validate({"start": bad, "end": 5, "label": "ID"})


def test_label_accepts_plain_string_value() -> None:
    assert Span.model_validate({"start": 0, "end": 1, "label": "CNIC"}).label is EntityType.CNIC


def test_with_spans_revalidates() -> None:
    doc = Document(doc_id="d1", text=TEXT)
    assert doc.with_spans([PATIENT]).spans == (PATIENT,)
    with pytest.raises(ValidationError):
        doc.with_spans([Span(start=0, end=999, label=EntityType.ID)])


def test_metadata_accepts_scalar_types() -> None:
    doc = Document(doc_id="d1", text="x", metadata={"family": "t01", "variant": 3, "noisy": True})
    assert Document.model_validate_json(doc.model_dump_json()) == doc


def test_prediction_validation_allows_overlap_but_checks_bounds() -> None:
    validate_spans_against_text(TEXT, [PATIENT, Span(start=10, end=20, label=EntityType.STAFF)])
    with pytest.raises(ValueError, match="exceeds"):
        validate_spans_against_text("abc", [Span(start=0, end=4, label=EntityType.ID)])
