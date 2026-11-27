"""Deterministic regex / rule-based PII detector (Milestone 3 baseline).

Rules were written from docs/ANNOTATION_GUIDE.md and observations of train/dev
documents only (CLAUDE.md rule 3). Context cues live in ``detectors/cues.py`` and are
lint-tested to occur in train/dev (review finding M3-1 removed 9 cues that did not).
Each rule yields candidate spans; overlaps are resolved by type priority (structured,
high-precision types first), then by longer span.

Known by-design weaknesses: names without a context cue, hospital acronyms,
addresses without an anchor word, and anything relying on meaning rather than
form. These are what the learned models are expected to handle better.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from privymed.detectors.base import Detector, trim_boundaries
from privymed.detectors.cues import (
    ID_KEYWORDS,
    PATIENT_FIELD_CUES,
    PATIENT_INLINE_CUES,
    STAFF_CUES,
    alternation,
)
from privymed.schema import EntityType, Span

# ----------------------------------------------------------------------------- vocab
_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_HOSP_SUFFIX = (
    r"(?:General\s+Hospital|Teaching\s+Hospital|Memorial\s+Hospital|Children's\s+Hospital|"
    r"Eye\s+Hospital|Surgical\s+Hospital|Hospital|Medical\s+(?:Centre|Center|Complex)|"
    r"Family\s+Clinic|Clinic|Polyclinic|Diagnostic\s+Centre|Laborator(?:y|ies)|"
    r"Health\s+Centre|Heart\s+Institute|Maternity\s+Home)"
)
# Pakistani cities: public geographic knowledge, used as address terminators.
_CITIES = (
    r"(?:Lahore|Karachi|Islamabad|Rawalpindi|Peshawar|Quetta|Multan|Faisalabad|Hyderabad|"
    r"Sialkot|Gujranwala|Abbottabad|Bahawalpur|Sargodha|Sukkur|Larkana|Mardan)"
)
_CAP = r"[A-Z][a-zA-Z'\-]+"  # a capitalised word
# Name parts are separated by exactly one space. Dev iteration 1: names crossed line breaks
# ("Name: X\nCNIC"); dev iteration 2: space runs in aligned forms ("Dr. X Y   Contact:").
_SP = r" "
# "Ali Khan", "Muhammad Ali Khan", "A. Khan", "Khan, Ali"
_NAME = rf"{_CAP},{_SP}{_CAP}(?:{_SP}{_CAP})?|{_CAP}(?:{_SP}{_CAP}){{0,2}}|[A-Z]\.{_SP}{_CAP}"
_NAME_CI = rf"[A-Za-z][A-Za-z'\-]+(?:{_SP}[A-Za-z][A-Za-z'\-]+){{0,2}}"  # UPPER/lower notes


@dataclass(frozen=True)
class Rule:
    label: EntityType
    pattern: re.Pattern[str]
    group: int | str = 0  # which group is the entity (lets a rule require context)


def _r(label: EntityType, pattern: str, group: int | str = 0, flags: int = 0) -> Rule:
    return Rule(label, re.compile(pattern, flags), group)


E = EntityType
RULES: tuple[Rule, ...] = (
    # --- EMAIL
    _r(E.EMAIL, r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    # --- CNIC: 13 digits as 5-7-1 (dashes, spaces or none)
    _r(E.CNIC, r"(?<![\d\-])\d{5}([- ]?)\d{7}\1\d(?![\d\-])"),
    # --- PHONE
    _r(E.PHONE, r"(?<![\w+])(?:\+92|0092|0)[ \-]?3\d{2}[ \-]?\d{3}[ \-]?\d{4}(?!\d)"),  # PK mobile
    _r(E.PHONE, r"\(0\d{2,3}\)\s?\d{6,8}(?!\d)"),  # (042) 35761234
    _r(E.PHONE, r"(?<![\w\-])0\d{2,3}-\d{6,8}(?![\d\-])"),  # 042-35761234
    _r(E.PHONE, r"\+92[ \-]?\d{2,3}[ \-]\d{6,8}(?!\d)"),  # +92 42 35761234
    _r(E.PHONE, r"\+44[ \-]?\d{2,4}[ \-]?\d{3,4}[ \-]?\d{3,4}(?!\d)"),  # UK international
    _r(E.PHONE, r"(?<!\d)0\d{2,4} \d{3,4} \d{4}(?!\d)"),  # UK national
    _r(E.PHONE, r"(?:\+1[ \-.]?)?(?:\(\d{3}\)\s?|\b\d{3}[ \-.])\d{3}[ \-.]\d{4}(?!\d)"),
    # --- DATE
    _r(E.DATE, r"(?<![\d/\-.])\d{4}-\d{2}-\d{2}(?![\d\-])"),  # ISO
    # A trailing "." is allowed unless a digit follows (unit test: "Seen on 12/03/2024.").
    _r(E.DATE, r"(?<![\d/\-.])\d{1,2}[/\-.]\d{1,2}[/\-.](?:\d{4}|\d{2})(?![\d/\-]|\.\d)"),
    _r(E.DATE, rf"\b\d{{1,2}}(?:st|nd|rd|th)?[\s\-]{_MONTHS}(?:[\s\-,]+\d{{4}})?\b", flags=re.I),
    _r(E.DATE, rf"\b{_MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b", flags=re.I),
    _r(E.DATE, rf"\b{_MONTHS}\s+\d{{4}}\b", flags=re.I),  # March 2024
    # --- ID: identifier shapes
    _r(E.ID, r"\bMRN-\d{4}-\d{4,}\b|\bMR\d{6,}\b|\bPT-\d{4,}\b|\bADM\d{5,}\b"),
    _r(E.ID, r"\bLAB\d{2}-\d{4,}\b|\bIP-\d{4}/\d{3,}\b|\b[A-Z]{2,4}/\d{2}/\d{4,}\b"),
    _r(E.ID, r"(?<![\w#])#\d{5,}\b|\b[A-Z]{2}\d{6,}\b"),
    # --- ID: context ("MRN: 12345", "Lab No: 1234-5678-12", "Accession: X")
    _r(
        E.ID,
        rf"(?i:(?<![\w#]){alternation(ID_KEYWORDS)}(?!\w)\.?\s*[:=#]?\s*)"
        r"(?P<v>[A-Z0-9][A-Z0-9/#\-]{3,}\d)",
        "v",
    ),
    # --- HOSPITAL: capitalised words + institution suffix
    _r(E.HOSPITAL, rf"\b(?:{_CAP}\s+){{1,3}}{_HOSP_SUFFIX}\b"),
    # --- ADDRESS: anchor word ... known city (optional postcode / country)
    _r(
        E.ADDRESS,
        rf"\b(?:House\s+No\.|House|H#|Flat|Plot|Mohallah|\d{{1,4}}-[A-Z],)[^\n]{{0,80}}?\b{_CITIES}"
        r"(?:\s\d{5})?(?:,\s*Pakistan)?\b",
        flags=re.I,
    ),
    _r(E.ADDRESS, rf"\b[A-Z][A-Za-z\-]+(?:\s+[A-Za-z0-9/\-]+){{0,3}},\s*{_CITIES}\b(?:\s\d{{5}})?"),
    # Iteration 3: address form fields (international addresses have no anchor word).
    _r(
        E.ADDRESS,
        r"(?i:\b(?:Residential\s+address|Correspondence\s+address|Address|ADDR)[ \t]*[:=][ \t]*)"
        r"(?P<v>[^\n;]+)",
        "v",
    ),
    # --- STAFF: name after a doctor title or a staff role cue
    _r(E.STAFF, rf"\b(?:Dr|Prof)\.?[ \t]+(?P<v>{_NAME})", "v"),
    _r(
        E.STAFF,
        rf"{alternation(STAFF_CUES)}[ \t]*:?[ \t]+"
        rf"(?:(?:Dr|Prof|Mr|Mrs|Ms)\.?[ \t]+)?(?P<v>{_NAME})",  # iter 2: "Clinician: Ms. X"
        "v",
    ),
    # --- PATIENT: name after a patient cue or a courtesy title
    # Form fields need a ':' / '=' (dev iteration 1: "NOK Contact:" captured "Contact").
    _r(
        E.PATIENT,
        rf"(?i:{alternation(PATIENT_FIELD_CUES)})[ \t]*[:=][ \t]*(?P<v>{_NAME})",
        "v",
    ),
    _r(E.PATIENT, rf"\b{alternation(PATIENT_INLINE_CUES)}[ \t]*:?[ \t]+(?P<v>{_NAME})", "v"),
    _r(E.PATIENT, rf"\b(?:Mr|Mrs|Ms)\.?[ \t]+(?P<v>{_NAME})", "v"),
    _r(E.PATIENT, rf"(?i:\b(?:NAME|PATIENT(?:[ \t]+NAME)?)[ \t]*[:=][ \t]*)(?P<v>{_NAME_CI})", "v"),
)

# Overlap resolution: higher priority wins; equal priority -> longer span.
PRIORITY: dict[EntityType, int] = {
    E.EMAIL: 9, E.CNIC: 8, E.PHONE: 7, E.ID: 6, E.DATE: 5,
    E.HOSPITAL: 4, E.ADDRESS: 3, E.STAFF: 2, E.PATIENT: 1,
}  # fmt: skip

_trim = trim_boundaries  # shared with Presidio (review finding M3-2)


class RegexDetector(Detector):
    """Rule-based baseline. Deterministic, CPU-only, no dependencies beyond ``re``."""

    name = "regex"

    def _candidates(self, text: str) -> Iterator[Span]:
        for rule in RULES:
            for m in rule.pattern.finditer(text):
                start, end = _trim(text, m.start(rule.group), m.end(rule.group))
                if end > start:
                    yield Span(start=start, end=end, label=rule.label, source=self.name)

    def _detect(self, text: str) -> list[Span]:
        ranked = sorted(
            self._candidates(text),
            key=lambda s: (-PRIORITY[s.label], -(s.end - s.start), s.start),
        )
        kept: list[Span] = []
        for cand in ranked:
            if not any(cand.overlaps(k) for k in kept):
                kept.append(cand)
        return kept
