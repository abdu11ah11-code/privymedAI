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


def test_case_mismatch_is_a_near_miss_not_a_hallucination() -> None:
    """Review M5-10: present-but-differently-cased text is not fabricated; still not mapped."""
    spans, stats = found("AYESHA KHAN", [Mention("Ayesha Khan", "PATIENT")])
    assert spans == [] and stats.near_miss == 1 and stats.hallucinated == 0


def test_whitespace_difference_is_a_near_miss() -> None:
    spans, stats = found("Ayesha\nKhan arrived", [Mention("Ayesha Khan", "PATIENT")])
    assert spans == [] and stats.near_miss == 1 and stats.hallucinated == 0


@pytest.mark.parametrize("text", ["Drew Barrett", "Patience Ali", "Missy Khan"])
def test_title_helper_keeps_names_that_start_like_titles(text: str) -> None:
    spans, _ = found(f"Seen by {text}.", [Mention(text, "STAFF")])
    assert spans == [(text, ST)]


def test_title_helper_strips_unspaced_and_role_titles() -> None:
    text = "Seen by Dr.Imran Ali and Nurse Ayesha Khan."
    mentions = [Mention("Dr.Imran Ali", "STAFF"), Mention("Nurse Ayesha Khan", "STAFF")]
    spans, _ = found(text, mentions)
    assert spans == [("Imran Ali", ST), ("Ayesha Khan", ST)]


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


@pytest.mark.parametrize(
    ("mention", "label", "expected"),
    [
        ("Dr. Kimberly Lloyd", "STAFF", ("Kimberly Lloyd", ST)),
        ("Mrs. Ayesha Khan", "PATIENT", ("Ayesha Khan", P)),
        ("Prof. Dr. Malik", "STAFF", ("Malik", ST)),
    ],
)
def test_leading_titles_stripped_from_names(
    mention: str, label: str, expected: tuple[str, EntityType]
) -> None:
    text = f"Seen by {mention} today."
    spans, _ = found(text, [Mention(mention, label)])
    assert spans == [expected]


def test_titles_not_stripped_from_other_types() -> None:
    text = "Ref: Dr. Ali Clinic"
    spans, _ = found(text, [Mention("Dr. Ali Clinic", "HOSPITAL")])
    assert spans == [("Dr. Ali Clinic", EntityType.HOSPITAL)]
