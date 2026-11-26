from __future__ import annotations

import pytest

from privymed.detectors import Detector
from privymed.schema import EntityType, Span


class _FixedDetector(Detector):
    name = "fixed"

    def __init__(self, spans: list[Span]) -> None:
        self._spans = spans

    def _detect(self, text: str) -> list[Span]:
        return list(self._spans)


def test_detect_returns_sorted_spans() -> None:
    late = Span(start=4, end=6, label=EntityType.ID)
    early = Span(start=0, end=2, label=EntityType.ID)
    assert [s.range for s in _FixedDetector([late, early]).detect("abcdefg")] == [(0, 2), (4, 6)]


def test_sort_is_deterministic_for_same_range_different_labels() -> None:
    a = Span(start=0, end=4, label=EntityType.STAFF)
    b = Span(start=0, end=4, label=EntityType.PATIENT)
    first = _FixedDetector([a, b]).detect("abcd")
    second = _FixedDetector([b, a]).detect("abcd")
    assert first == second
    assert [s.label for s in first] == [EntityType.PATIENT, EntityType.STAFF]


def test_detect_stamps_source_with_detector_name() -> None:
    (span,) = _FixedDetector([Span(start=0, end=2, label=EntityType.ID)]).detect("abc")
    assert span.source == "fixed"


def test_detect_keeps_explicit_sub_source() -> None:
    explicit = Span(start=0, end=2, label=EntityType.ID, source="fixed:rule7")
    (span,) = _FixedDetector([explicit]).detect("abc")
    assert span.source == "fixed:rule7"


def test_detect_rejects_out_of_bounds_prediction() -> None:
    det = _FixedDetector([Span(start=0, end=50, label=EntityType.ID)])
    with pytest.raises(ValueError, match="exceeds"):
        det.detect("short")


def test_detect_batch() -> None:
    det = _FixedDetector([])
    assert det.detect_batch(["a", "b"]) == [[], []]


def test_detector_is_abstract() -> None:
    with pytest.raises(TypeError):
        Detector()  # type: ignore[abstract]


def test_concrete_detector_must_define_name() -> None:
    with pytest.raises(TypeError, match="name"):

        class _Nameless(Detector):
            def _detect(self, text: str) -> list[Span]:
                return []
