"""Microsoft Presidio baseline, configured for the PrivyMed schema (Milestone 3).

Configuration principle: adapt Presidio *to the target schema* (entity
mapping, boundary conventions of the annotation guide, phone regions, score
threshold) and add custom recognizers only for entity types Presidio has no
concept of (Pakistani CNIC, medical record identifiers).

What is shared with the regex baseline (disclosed; Milestone 3 review M3-3):
    * the ID keywords and the staff role cues (``detectors/cues.py``), and the
      letter-prefix / ``#`` ID shapes. Presidio has no record-number entity and no
      clinical-role concept, so its ID scores and its STAFF/PATIENT split are
      effectively "Presidio + the shared cue rules";
    * the boundary helper ``trim_boundaries``.
    What is *not* shared: name, date, phone, hospital and address detection, which
    come from Presidio's recognizers and spaCy NER only.

Pipeline
    1. AnalyzerEngine (spaCy ``en_core_web_lg``) restricted to schema-relevant
       entities; US-specific and financial recognizers are not requested.
    2. PhoneRecognizer with regions PK, GB, US (default lacks PK).
    3. Custom recognizers: ``PK_CNIC`` (PatternRecognizer, base 0.5, boosted to
       0.85 by Presidio's context enhancer near "CNIC"), and ``RECORD_ID``
       (EntityRecognizer: 0.6 after an ID keyword, 0.5 for prefix shapes; it has no
       context words, so it is never boosted — at thresholds >= 0.7 all IDs drop).
    4. Map Presidio entities to the 9-type schema (see ``ENTITY_MAP``).
    5. Normalise boundaries to the annotation guide: strip leading role/title
       words ("Patient", "Dr.") from PERSON, then ``trim_boundaries`` (balanced
       parentheses are kept, so "(042) 35761234" stays intact).
    6. Split PERSON into STAFF (doctor title or staff role cue just before the
       name) and PATIENT (everything else) — Presidio has a single PERSON type.
    7. Drop out-of-schema DATE_TIME hits (times of day; relative dates with no
       digit and no month name), per the annotation guide; drop ORG/PERSON/LOCATION
       hits that are generic clinical field abbreviations ("MRN", "CNIC", "ICU").
    8. Resolve overlaps: pattern-validated types (email/phone/CNIC/ID) beat NER
       types, then higher score, then longer span.
"""

from __future__ import annotations

import re
import threading
from typing import TYPE_CHECKING, Any

from privymed.detectors.base import Detector, strip_leading_title, trim_boundaries
from privymed.detectors.cues import ID_KEYWORDS, STAFF_CUES, alternation
from privymed.schema import EntityType, Span

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine

E = EntityType
ENTITY_MAP: dict[str, EntityType] = {
    "PERSON": E.PATIENT,  # refined to STAFF/PATIENT in step 6
    "EMAIL_ADDRESS": E.EMAIL,
    "PHONE_NUMBER": E.PHONE,
    "DATE_TIME": E.DATE,
    "LOCATION": E.ADDRESS,
    "ORGANIZATION": E.HOSPITAL,
    "PK_CNIC": E.CNIC,
    "RECORD_ID": E.ID,
}
REQUESTED = tuple(ENTITY_MAP)

_STAFF_CUE = re.compile(rf"(?:\b(?:dr|prof)\.?|\b{alternation(STAFF_CUES)})\s*:?\s*$", re.I)
_MONTH = re.compile(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b")
_TIME_ONLY = re.compile(r"(?i)^\d{1,2}[:.]\d{2}(?:\s?[ap]\.?m\.?)?$")
# Recognizers validated by structure beat NER on overlap (spaCy tags phone numbers and
# record ids as DATE with 0.85; smoke test on a synthetic sentence).
# Overlap priority (higher wins): validated patterns, most specific first, then NER types.
_PRIORITY = {"EMAIL_ADDRESS": 4, "PK_CNIC": 3, "RECORD_ID": 2, "PHONE_NUMBER": 1}
# Generic clinical field abbreviations that spaCy tags as ORG/PERSON/GPE (smoke test:
# "CNIC" and "MRN" became HOSPITAL). Generic vocabulary, not tuned to any split.
_FIELD_WORDS = frozenset(
    {
        "mrn", "mr", "cnic", "nic", "dob", "opd", "ipd", "icu", "ccu", "hdu", "er", "ent",
        "bp", "hr", "rr", "nok", "id", "ecg", "ekg", "cxr", "us", "ct", "mri", "rx", "dx",
        "pt", "lab", "ward", "reg", "addr", "ph", "tel", "fax", "email",
    }
)  # fmt: skip


def _build_analyzer() -> AnalyzerEngine:
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import (
        DateRecognizer,
        EmailRecognizer,
        PhoneRecognizer,
        SpacyRecognizer,
    )

    nlp = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=["en"])
    registry.add_recognizer(SpacyRecognizer(supported_language="en"))
    registry.add_recognizer(EmailRecognizer())
    registry.add_recognizer(DateRecognizer())
    registry.add_recognizer(PhoneRecognizer(supported_regions=("PK", "GB", "US")))
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="PK_CNIC",
            name="PkCnicRecognizer",
            patterns=[Pattern("cnic_5_7_1", r"\b\d{5}[- ]?\d{7}[- ]?\d\b", 0.5)],
            context=["cnic", "nic", "identity", "national"],
        )
    )
    registry.add_recognizer(_record_id_recognizer())
    return AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=["en"])


# Record identifiers: (a) any identifier directly after an ID keyword, or (b) identifiers
# whose shape alone marks them as ids (letter prefix + digits, or '#'+digits). A generic
# "any digit group" pattern matched phone numbers and dates (smoke test), so it is not used.
_ID_KEYED = re.compile(
    rf"(?i:(?<![\w#]){alternation(ID_KEYWORDS)}(?!\w)\.?[ \t]*[:=#]?[ \t]*)"
    r"(?P<v>#?[A-Z0-9][A-Z0-9/#\-]{3,}(?<=\d))"
)
_ID_SHAPED = re.compile(r"(?<![\w#])(?:#\d{5,}|[A-Z]{2,4}[-/]?\d{2,}(?:[-/]\d{2,})*)\b")


def _record_id_recognizer() -> Any:
    from presidio_analyzer import EntityRecognizer, RecognizerResult

    class RecordIdRecognizer(EntityRecognizer):
        """Custom recognizer: Presidio has no medical-record-number entity."""

        def load(self) -> None:
            pass

        def analyze(self, text: str, entities: list[str], nlp_artifacts: Any = None) -> list[Any]:
            out = [
                RecognizerResult("RECORD_ID", m.start("v"), m.end("v"), 0.6)
                for m in _ID_KEYED.finditer(text)
            ]
            out += [
                RecognizerResult("RECORD_ID", m.start(), m.end(), 0.5)
                for m in _ID_SHAPED.finditer(text)
            ]
            return out

    return RecordIdRecognizer(supported_entities=["RECORD_ID"], name="RecordIdRecognizer")


class PresidioDetector(Detector):
    """Presidio Analyzer + spaCy ``en_core_web_lg``, mapped to the PrivyMed schema."""

    name = "presidio"

    # 0.3 = best strict F1 in the dev-only sweep (E-002; tie with 0.4 -> lower threshold).
    def __init__(self, score_threshold: float = 0.3) -> None:
        self.score_threshold = score_threshold
        self._analyzer: AnalyzerEngine | None = None
        self._lock = threading.Lock()

    @property
    def analyzer(self) -> AnalyzerEngine:
        """Built once on first use; locked so concurrent first calls build it only once."""
        if self._analyzer is None:
            with self._lock:
                if self._analyzer is None:
                    self._analyzer = _build_analyzer()
        return self._analyzer

    def config(self) -> dict[str, Any]:
        return {
            "score_threshold": self.score_threshold,
            "spacy_model": "en_core_web_lg",
            "entities": list(REQUESTED),
            "phone_regions": ["PK", "GB", "US"],
        }

    def _detect(self, text: str) -> list[Span]:
        results = self.analyzer.analyze(
            text=text,
            language="en",
            entities=list(REQUESTED),
            score_threshold=self.score_threshold,
        )
        candidates: list[tuple[int, float, Span]] = []
        for r in results:
            span = self._to_span(text, r.entity_type, r.start, r.end)
            if span is not None:
                candidates.append((_PRIORITY.get(r.entity_type, 0), float(r.score), span))
        # Priority (pattern types by specificity), then higher score, then longer span.
        candidates.sort(key=lambda c: (-c[0], -c[1], -(c[2].end - c[2].start), c[2].start))
        kept: list[Span] = []
        for _, score, span in candidates:
            if not any(span.overlaps(k) for k in kept):
                kept.append(span.model_copy(update={"score": min(1.0, score)}))
        return kept

    def _to_span(self, text: str, entity: str, start: int, end: int) -> Span | None:
        label = ENTITY_MAP.get(entity)
        if label is None:
            return None
        if entity == "PERSON":
            start = strip_leading_title(text, start, end)
        start, end = trim_boundaries(text, start, end)
        if end <= start:
            return None
        surface = text[start:end]
        if label is E.DATE and (
            _TIME_ONLY.match(surface)
            or not (any(c.isdigit() for c in surface) or _MONTH.search(surface))
        ):
            return None  # times / relative dates are out of schema (annotation guide)
        if entity in ("ORGANIZATION", "PERSON", "LOCATION") and surface.lower() in _FIELD_WORDS:
            return None
        if entity == "PERSON" and _STAFF_CUE.search(text[max(0, start - 30) : start]):
            label = E.STAFF
        return Span(start=start, end=end, label=label, source=self.name)
