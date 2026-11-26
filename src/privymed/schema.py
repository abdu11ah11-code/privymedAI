"""Core data contracts shared by every component.

Design decision (ADR-001): character-offset spans are the single source of
truth for both gold annotations and system predictions. BIO tags are derived
from spans only for transformer training. This lets rules, Presidio, the LLM
and the transformer be evaluated by one span-based evaluator without
tokenizer artifacts.

Offsets are Python ``str`` indices, i.e. **Unicode code points** (not bytes,
not UTF-16 units). Detectors must report offsets into the *original* text,
never into a normalised copy. The frontend must convert to UTF-16 indices
before highlighting.

Comparison rule: ``Span.__eq__`` compares *all* fields (including ``score``
and ``source``). Evaluation and fusion must compare ``span.key`` or
``span.range`` instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GOLD_SOURCE = "gold"

# Characters that str.strip() keeps but that must not sit at a span boundary.
_INVISIBLE = "​‌‍⁠﻿"


class EntityType(StrEnum):
    """The 9-type annotation schema (finalised in Milestone 0)."""

    PATIENT = "PATIENT"  # patient and patient-family names
    STAFF = "STAFF"  # doctors, nurses, other clinical staff names
    DATE = "DATE"  # dates and dates of birth
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    CNIC = "CNIC"  # Pakistani national ID: 5-7-1 digits
    ID = "ID"  # MRNs, patient IDs, other record identifiers
    ADDRESS = "ADDRESS"
    HOSPITAL = "HOSPITAL"  # hospitals, clinics, labs


class Span(BaseModel):
    """A labelled half-open character interval ``[start, end)`` in a document."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    start: int = Field(ge=0)
    end: int = Field(ge=1)
    label: EntityType
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default=GOLD_SOURCE, min_length=1)
    # Surface-format tag for gold spans (e.g. "dmy_slash"); used for error breakdowns.
    fmt: str | None = None

    @field_validator("label", mode="before")
    @classmethod
    def _coerce_label(cls, value: object) -> object:
        # Strict mode would reject plain strings from JSON; allow exact enum values only.
        if isinstance(value, str) and not isinstance(value, EntityType):
            return EntityType(value)
        return value

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"span end ({self.end}) must be > start ({self.start})")
        return self

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def range(self) -> tuple[int, int]:
        """Boundaries only — use for boundary/type-agnostic matching."""
        return (self.start, self.end)

    @property
    def key(self) -> tuple[int, int, EntityType]:
        """Boundaries + label — use for strict matching and de-duplication."""
        return (self.start, self.end, self.label)

    def overlaps(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end


def span_sort_key(span: Span) -> tuple[int, int, str, str]:
    """Total, deterministic ordering for spans (ties broken by label, source)."""
    return (span.start, span.end, span.label.value, span.source)


def validate_spans_against_text(text: str, spans: Iterable[Span]) -> None:
    """Raise ``ValueError`` if any span falls outside ``text``.

    Used for system predictions, which (unlike gold spans) may overlap.
    """
    n = len(text)
    for span in spans:
        if span.end > n:
            raise ValueError(f"span {span.start}:{span.end} exceeds text length {n}")


MetadataValue = str | int | float | bool


class Document(BaseModel):
    """A gold-annotated document.

    Annotation rules enforced here (gold data only):
    * spans lie inside the text,
    * spans do not overlap,
    * spans do not start or end with whitespace or invisible characters.
    Spans are stored sorted by :func:`span_sort_key`.

    Never build modified documents with ``model_copy(update=...)`` or
    ``model_construct`` — both skip validation. Use :meth:`with_spans`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str = Field(min_length=1)
    text: str
    spans: tuple[Span, ...] = ()
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("spans")
    @classmethod
    def _sort_spans(cls, spans: tuple[Span, ...]) -> tuple[Span, ...]:
        return tuple(sorted(spans, key=span_sort_key))

    @model_validator(mode="after")
    def _check_spans(self) -> Self:
        validate_spans_against_text(self.text, self.spans)
        for span in self.spans:
            surface = self.text[span.start : span.end]
            if surface != surface.strip().strip(_INVISIBLE) or not surface.strip():
                raise ValueError(
                    f"{self.doc_id}: span {span.start}:{span.end} has leading/trailing "
                    "whitespace or invisible characters"
                )
        for prev, cur in zip(self.spans, self.spans[1:], strict=False):
            if prev.overlaps(cur):
                raise ValueError(
                    f"{self.doc_id}: overlapping gold spans {prev.start}:{prev.end} "
                    f"and {cur.start}:{cur.end}"
                )
        return self

    def span_text(self, span: Span) -> str:
        return self.text[span.start : span.end]

    def with_spans(self, spans: Iterable[Span]) -> Document:
        """Return a copy with new spans, fully re-validated."""
        return Document.model_validate(
            {
                "doc_id": self.doc_id,
                "text": self.text,
                "spans": tuple(spans),
                "metadata": dict(self.metadata),
            }
        )
