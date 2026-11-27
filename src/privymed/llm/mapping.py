"""Map LLM-returned entity strings to character spans, and count what cannot be mapped.

An instruction-following LLM answers with *strings* (``{"text": "Ayesha Khan",
"type": "PATIENT"}``), not offsets. Mapping rules (documented in docs/EVALUATION.md):

* Every whole-word, case-sensitive occurrence of a returned string is labelled
  (gold labels every mention; an LLM typically lists a repeated name once).
* "Whole word": the character before and after the occurrence must not be a letter
  or digit, so "Ali" does not match inside "Alina" or "Ali2".
* A string that occurs nowhere in the text is a **hallucination** (counted, dropped).
* An unknown entity type is **invalid** (counted, dropped).
* The same string returned with two different types: the first type wins (counted).
* Overlapping candidate spans: the longer span wins (then the earlier one).
* Boundaries are normalised with the shared ``trim_boundaries`` helper, and leading
  titles (Dr., Prof., Mr., Mrs., Ms.) are stripped from PATIENT/STAFF spans (guide rule).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from privymed.detectors.base import trim_boundaries
from privymed.schema import EntityType, Span

_TYPES = {t.value for t in EntityType}
_LEADING_TITLE = re.compile(r"(?:(?:dr|prof|mr|mrs|ms|miss)\b\.?\s+)+", re.IGNORECASE)


@dataclass
class MappingStats:
    """Counts for one or many documents (add with ``+``)."""

    documents: int = 0
    parse_failures: int = 0  # response was not valid JSON matching the schema
    mentions: int = 0  # entity objects returned
    hallucinated: int = 0  # returned text not found in the document
    invalid_type: int = 0  # type outside the 9-type schema
    type_conflicts: int = 0  # same text returned with different types
    occurrences: int = 0  # spans produced after mapping

    def __add__(self, other: MappingStats) -> MappingStats:
        return MappingStats(
            **{k: getattr(self, k) + getattr(other, k) for k in self.__dataclass_fields__}
        )


@dataclass(frozen=True)
class Mention:
    text: str
    label: str


def parse_response(raw: str) -> list[Mention] | None:
    """Parse ``{"entities": [{"text": ..., "type": ...}, ...]}``; None if malformed."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    items = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out: list[Mention] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        text, label = item.get("text"), item.get("type")
        if not isinstance(text, str) or not isinstance(label, str):
            return None
        out.append(Mention(text=text, label=label.strip().upper()))
    return out


def _occurrences(text: str, needle: str) -> list[int]:
    """Start offsets of whole-word, case-sensitive occurrences of ``needle``."""
    starts, i = [], text.find(needle)
    while i != -1:
        before = text[i - 1] if i > 0 else ""
        after = text[i + len(needle)] if i + len(needle) < len(text) else ""
        if not (before.isalnum() or after.isalnum()):
            starts.append(i)
        i = text.find(needle, i + 1)
    return starts


def map_mentions(
    text: str, mentions: Sequence[Mention], source: str = "llm"
) -> tuple[list[Span], MappingStats]:
    """Turn LLM mentions into non-overlapping character spans plus mapping statistics."""
    stats = MappingStats(documents=1, mentions=len(mentions))
    first_type: dict[str, str] = {}
    candidates: list[Span] = []
    for m in mentions:
        needle = m.text.strip()
        if m.label not in _TYPES:
            stats.invalid_type += 1
            continue
        if not needle:
            stats.hallucinated += 1
            continue
        if needle in first_type:
            if first_type[needle] != m.label:
                stats.type_conflicts += 1
            continue  # already mapped (all occurrences)
        starts = _occurrences(text, needle)
        if not starts:
            stats.hallucinated += 1
            continue
        first_type[needle] = m.label
        for s in starts:
            a, b = trim_boundaries(text, s, s + len(needle))
            if m.label in ("PATIENT", "STAFF"):
                # Guide: titles are not part of a name. Qwen kept "Dr." in 40 of 63 dev STAFF
                # mentions despite the instruction; same normalisation as the Presidio baseline.
                title = _LEADING_TITLE.match(text, a, b)
                if title:
                    a = title.end()
            if b > a:
                candidates.append(Span(start=a, end=b, label=EntityType(m.label), source=source))
    candidates.sort(key=lambda s: (-(s.end - s.start), s.start))
    kept: list[Span] = []
    for c in candidates:
        if not any(c.overlaps(k) for k in kept):
            kept.append(c)
    kept.sort(key=lambda s: s.start)
    stats.occurrences = len(kept)
    return kept, stats
