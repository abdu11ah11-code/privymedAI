"""Context-cue vocabulary shared by the rule-based parts of the regex and Presidio baselines.

Protocol (CLAUDE.md rule 3; Milestone 3 review finding M3-1): every cue here must
occur in **train or dev** text. This is enforced by ``tests/test_cues.py``.

Why this module exists: the generator's author also wrote the rules, so cue words
from test-only templates ("Prescriber", "Lab No", "Booking reference", "Booked for",
"Rx No") leaked into both baselines in commit fb8f068. They occurred 0 times in
train/dev. Keeping every cue in one list makes that kind of leak testable.

Disclosure: the Presidio baseline uses these same cue lists (for its custom record-id
recognizer and the PERSON -> STAFF/PATIENT split), because Presidio has no concept of
record numbers or clinical roles. The comparison is therefore "Presidio + shared cues"
vs "regex + shared cues" on those two aspects.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# "<keyword>: <identifier>"
ID_KEYWORDS: tuple[str, ...] = (
    "MRN", "MR#", "Patient ID", "ID", "Accession", "Admission No", "Specimen ID", "Claim ref",
)  # fmt: skip

# "<role cue>: [Dr.] <staff name>"
STAFF_CUES: tuple[str, ...] = (
    "Seen by", "Signed", "Verified by", "Reported by", "Referring doctor", "Referring physician",
    "Consultant", "Admitting Doctor", "Clinician", "Processed by", "Dict.",
)  # fmt: skip

# Form fields "<cue>: <patient name>" (a ':' or '=' is required after these)
PATIENT_FIELD_CUES: tuple[str, ...] = (
    "Patient", "Patient name", "Full Name", "Name", "Policy holder", "Insured member",
    "Next of Kin", "NOK", "Guardian/NOK",
)  # fmt: skip

# Inline "<cue> <patient name>" (no ':' needed)
PATIENT_INLINE_CUES: tuple[str, ...] = ("Pt", "Re", "Appt for")

ALL_CUES: tuple[str, ...] = ID_KEYWORDS + STAFF_CUES + PATIENT_FIELD_CUES + PATIENT_INLINE_CUES


def cue_pattern(cue: str) -> str:
    """Regex for one cue: escaped, any whitespace run between words."""
    return r"\s+".join(re.escape(word) for word in cue.split())


def alternation(cues: Iterable[str]) -> str:
    """Non-capturing alternation, longest cue first so 'Patient name' beats 'Patient'."""
    return "(?:" + "|".join(cue_pattern(c) for c in sorted(cues, key=len, reverse=True)) + ")"
