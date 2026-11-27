"""Prompt for the LLM baseline: instructions from the annotation guide + train-only examples.

CLAUDE.md rule 3: instructions are written from docs/ANNOTATION_GUIDE.md, and few-shot
examples are drawn **from the train split only**, chosen by a deterministic rule (short
documents that together cover the most entity types). The full prompt and its SHA-256
are recorded in every evaluation report.
"""

from __future__ import annotations

import hashlib
import json
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
- If there is no PII, return {"entities": []}."""

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


def select_examples(train: Sequence[Document], k: int = 3, max_words: int = 70) -> list[Document]:
    """Deterministically pick ``k`` short train documents that cover the most entity types.

    Greedy set cover over entity types; ties broken by fewer words, then doc_id.
    """
    pool = sorted(
        (d for d in train if d.spans and len(d.text.split()) <= max_words),
        key=lambda d: (len(d.text.split()), d.doc_id),
    )
    chosen: list[Document] = []
    covered: set[EntityType] = set()
    for _ in range(k):
        best = max(
            (d for d in pool if d not in chosen),
            key=lambda d: (len({s.label for s in d.spans} - covered), -len(d.text.split())),
            default=None,
        )
        if best is None:
            break
        chosen.append(best)
        covered |= {s.label for s in best.spans}
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
        {"instructions": INSTRUCTIONS, "schema": RESPONSE_SCHEMA,
         "examples": [(e.doc_id, e.text, gold_answer(e)) for e in examples]},
        sort_keys=True,
    )  # fmt: skip
    return {
        "example_doc_ids": [e.doc_id for e in examples],
        "sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
    }
