"""String-to-offset mapping and response parsing for the LLM baseline (no model needed)."""

from __future__ import annotations

import pytest

from privymed.llm.mapping import MappingStats, Mention, map_mentions, parse_response
from privymed.schema import EntityType

P, ST, PH = EntityType.PATIENT, EntityType.STAFF, EntityType.PHONE


def found(text: str, mentions: list[Mention]) -> tuple[list[tuple[str, EntityType]], MappingStats]:
    spans, stats = map_mentions(text, mentions)
    return [(text[s.start : s.end], s.label) for s in spans], stats


def test_every_whole_word_occurrence_is_labelled() -> None:
    text = "Ali Khan seen. Mr. Khan called; Khanzada is someone else."
    spans, stats = found(text, [Mention("Khan", "PATIENT")])
    assert spans == [("Khan", P), ("Khan", P)]  # not inside "Khanzada"
    assert stats.occurrences == 2 and stats.hallucinated == 0


def test_substring_inside_word_is_not_a_match() -> None:
    spans, stats = found("Alina and Ali2", [Mention("Ali", "PATIENT")])
    assert spans == [] and stats.hallucinated == 1


def test_hallucinated_and_invalid_type_are_counted() -> None:
    _, stats = found("Patient Ayesha.", [Mention("Fatima", "PATIENT"), Mention("Ayesha", "NAME")])
    assert (stats.hallucinated, stats.invalid_type, stats.occurrences) == (1, 1, 0)


def test_type_conflict_keeps_first_type() -> None:
    spans, stats = found("Dr. Imran", [Mention("Imran", "STAFF"), Mention("Imran", "PATIENT")])
    assert spans == [("Imran", ST)] and stats.type_conflicts == 1


def test_longer_overlapping_span_wins() -> None:
    text = "Ali Khan arrived"
    spans, _ = found(text, [Mention("Ali", "PATIENT"), Mention("Ali Khan", "PATIENT")])
    assert spans == [("Ali Khan", P)]


def test_boundaries_trimmed_and_parentheses_kept() -> None:
    text = "Tel: (042) 35761234."
    spans, _ = found(text, [Mention("(042) 35761234", "PHONE")])
    assert spans == [("(042) 35761234", PH)]


def test_case_sensitive_matching() -> None:
    spans, stats = found("AYESHA KHAN", [Mention("Ayesha Khan", "PATIENT")])
    assert spans == [] and stats.hallucinated == 1


@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        ('{"entities": [{"text": "Ali", "type": "patient"}]}', True),
        ('{"entities": []}', True),
        ("not json", False),
        ('{"entities": [{"text": 5, "type": "ID"}]}', False),
        ('{"items": []}', False),
        ('[{"text": "Ali", "type": "PATIENT"}]', False),
    ],
)
def test_parse_response(raw: str, ok: bool) -> None:
    parsed = parse_response(raw)
    assert (parsed is not None) is ok
    if raw.startswith('{"entities": [{"text": "Ali"'):
        assert parsed == [Mention("Ali", "PATIENT")]  # type upper-cased


def test_stats_add() -> None:
    a = MappingStats(documents=1, mentions=2, hallucinated=1)
    b = MappingStats(documents=1, parse_failures=1)
    assert (a + b) == MappingStats(documents=2, mentions=2, hallucinated=1, parse_failures=1)
