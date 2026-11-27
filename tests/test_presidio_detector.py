"""Presidio baseline: schema mapping and configuration fixes (loads spaCy en_core_web_lg)."""

from __future__ import annotations

import pytest

pytest.importorskip("presidio_analyzer")
pytest.importorskip("en_core_web_lg")

from privymed.detectors.presidio import PresidioDetector
from privymed.schema import EntityType

pytestmark = pytest.mark.slow
E = EntityType
SENTENCE = (
    "Patient Ayesha Khan, ph 0300-1234567, CNIC 35202-1234567-1, seen by Dr. Imran Malik at "
    "Crescent Medical Centre on 12/03/2024. Email ali@gmail.com. MRN: 7159-0324-03. "
    "Review at 10:30 AM yesterday."
)


@pytest.fixture(scope="module")
def det() -> PresidioDetector:
    return PresidioDetector()


@pytest.fixture(scope="module")
def found(det: PresidioDetector) -> set[tuple[str, EntityType]]:
    return {(SENTENCE[s.start : s.end], s.label) for s in det.detect(SENTENCE)}


@pytest.mark.parametrize(
    ("surface", "label"),
    [
        ("Ayesha Khan", E.PATIENT),  # leading "Patient" stripped (guide: titles excluded)
        ("Imran Malik", E.STAFF),  # PERSON after "Dr." -> STAFF
        ("0300-1234567", E.PHONE),  # was DATE in default Presidio
        ("35202-1234567-1", E.CNIC),  # custom recognizer
        ("7159-0324-03", E.ID),  # keyed custom recognizer; was DATE / PHONE before
        ("Crescent Medical Centre", E.HOSPITAL),  # ORGANIZATION -> HOSPITAL
        ("12/03/2024", E.DATE),
        ("ali@gmail.com", E.EMAIL),
    ],
)
def test_configured_presidio_gets_smoke_sentence_right(
    found: set[tuple[str, EntityType]], surface: str, label: EntityType
) -> None:
    assert (surface, label) in found


def test_out_of_schema_hits_are_dropped(found: set[tuple[str, EntityType]]) -> None:
    surfaces = {s for s, _ in found}
    assert "10:30 AM" not in surfaces  # time of day
    assert "yesterday" not in surfaces  # relative date
    assert "CNIC" not in surfaces and "MRN" not in surfaces  # field labels, not organisations


def test_no_overlapping_output_and_scores_kept(det: PresidioDetector) -> None:
    spans = det.detect(SENTENCE)
    assert all(not a.overlaps(b) for i, a in enumerate(spans) for b in spans[i + 1 :])
    assert all(0.0 < s.score <= 1.0 and s.source == "presidio" for s in spans)


def test_threshold_filters_low_confidence(det: PresidioDetector) -> None:
    strict = PresidioDetector(score_threshold=0.95)
    high = strict.detect(SENTENCE)
    assert len(high) < len(det.detect(SENTENCE))
    assert all(s.score >= 0.95 for s in high)
