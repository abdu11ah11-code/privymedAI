"""Prompt for the LLM baseline: instructions from the annotation guide + train-only examples.

CLAUDE.md rule 3: instructions are written from docs/ANNOTATION_GUIDE.md, and few-shot
examples are drawn **from the train split only**, chosen by a deterministic rule (short
documents that together cover the most entity types). The full prompt and its SHA-256
are recorded in every evaluation report, and the full prompt text is written next to the
raw model outputs (``reports/eval/raw/``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from privymed.schema import Document, EntityType

INSTRUCTIONS = """You are a de-identification system for clinical notes. Find every piece of
personally identifying information (PII) in the note and return it as JSON.

Entity types (use exactly these names):
- PATIENT: names of patients and of their relatives (e.g. mother, husband, guardian).
- STAFF: names of doctors, nurses and other clinical staff.
- DATE: calendar dates, including dates of birth and partial dates like "12 March" or "March 2024".
- PHONE: phone or fax numbers, including country codes and parentheses.
- EMAIL: email addresses.
- CNIC: Pakistani national identity numbers (13 digits, often written 12345-1234567-1).
- ID: medical record numbers, patient IDs, lab, admission, accession and other record numbers.
- ADDRESS: street addresses and locations that are part of an address.
- HOSPITAL: names or acronyms of hospitals, clinics and laboratories.

Rules:
- Copy each entity's text EXACTLY as it appears in the note (same spelling and capitalisation).
- Do NOT include titles (Dr., Mr., Mrs., Ms., Prof.), credentials (MBBS, FCPS) or field labels
  ("MRN:", "Name:", "DOB:") in the text.
- Do NOT return times of day, relative dates ("yesterday", "two weeks ago"), ages, diagnoses,
  medications, or a city mentioned alone outside an address.
- List each distinct entity once; it will be matched everywhere it occurs.
- HOSPITAL: do not include a department, specialty or city that follows in parentheses
  ("Crescent Hospital (Cardiology)" -> "Crescent Hospital"). Generic references such as
  "the hospital", "OPD" or "ward 4" are not entities.
- ID: keep prefixes that are part of the identifier and joined by "-" or "#"
  ("MRN-2024-001234", "#1913619"), but never a field label ending in ":" or "="
  ("MRN:7159" -> "7159").
- DATE: a month name on its own ("in June", "May" used as a word) is not a date.
- Names: do not include a possessive "'s".
- If there is no PII, return {"entities": []}."""

# v1 (E-006 first runs, commit a3abe6b): no boundary rules beyond titles/labels, and few-shot
# selection by entity types only. v2 (review M5-2/M5-3): the guide's HOSPITAL / ID / DATE /
# possessive boundary rules, and examples chosen to also cover conventions and distinct families.
PROMPT_VERSION = "v2"

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": [t.value for t in EntityType]},
                },
                "required": ["text", "type"],
            },
        }
    },
    "required": ["entities"],
}


def gold_answer(doc: Document) -> str:
    """The JSON answer the model should produce for a gold document (distinct mentions)."""
    seen: dict[str, str] = {}
    for s in doc.spans:
        seen.setdefault(doc.span_text(s), s.label.value)
    return json.dumps({"entities": [{"text": t, "type": lab} for t, lab in seen.items()]})


_TITLE_BEFORE = re.compile(r"(?i)\b(?:dr|prof|mr|mrs|ms)\.?\s$")


def example_features(doc: Document) -> set[str]:
    """Entity types plus the guide's boundary conventions a document demonstrates."""
    feats = {s.label.value for s in doc.spans}
    for s in doc.spans:
        before, after = doc.text[max(0, s.start - 5) : s.start], doc.text[s.end : s.end + 2]
        if s.label in (EntityType.PATIENT, EntityType.STAFF) and _TITLE_BEFORE.search(before):
            feats.add("title_before_name")
        if s.label is EntityType.HOSPITAL and after.startswith(" ("):
            feats.add("parenthesis_after_hospital")
        if before.endswith((":", "=")) and s.label in (EntityType.ID, EntityType.CNIC):
            feats.add("field_label_glued")
    return feats


def _families(doc: Document) -> set[str]:
    return set(str(doc.metadata.get("family", doc.doc_id)).split("+"))


def select_examples(train: Sequence[Document], k: int = 3, max_words: int = 90) -> list[Document]:
    """Deterministically pick ``k`` short train documents for the few-shot prompt.

    Greedy cover over entity types *and* boundary conventions (``example_features``), never
    reusing a template family (v1 picked two near-identical rad_brief notes — review M5-3).
    Ties: fewer words, then doc_id. Train split only (CLAUDE.md rule 3).
    """
    pool = sorted(
        (d for d in train if d.spans and len(d.text.split()) <= max_words),
        key=lambda d: (len(d.text.split()), d.doc_id),
    )
    chosen: list[Document] = []
    covered: set[str] = set()
    used_families: set[str] = set()
    for _ in range(k):
        candidates = [d for d in pool if d not in chosen and not (_families(d) & used_families)]
        best = max(
            candidates,
            key=lambda d: (len(example_features(d) - covered), -len(d.text.split())),
            default=None,
        )
        if best is None:
            break
        chosen.append(best)
        covered |= example_features(best)
        used_families |= _families(best)
    return chosen


def build_messages(examples: Sequence[Document], text: str) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": INSTRUCTIONS}]
    for ex in examples:
        messages.append({"role": "user", "content": f"Note:\n{ex.text}"})
        messages.append({"role": "assistant", "content": gold_answer(ex)})
    messages.append({"role": "user", "content": f"Note:\n{text}"})
    return messages


def prompt_fingerprint(examples: Sequence[Document]) -> dict[str, object]:
    """Prompt identity for reports: example ids and a hash of everything except the note."""
    template = json.dumps(
        {"version": PROMPT_VERSION, "instructions": INSTRUCTIONS, "schema": RESPONSE_SCHEMA,
         "examples": [(e.doc_id, e.text, gold_answer(e)) for e in examples]},
        sort_keys=True,
    )  # fmt: skip
    return {
        "version": PROMPT_VERSION,
        "example_doc_ids": [e.doc_id for e in examples],
        "example_features": sorted(set().union(*(example_features(e) for e in examples))),
        "sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
    }
