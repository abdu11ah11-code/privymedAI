"""The common interface every detection system implements.

Regex, Presidio, the fine-tuned transformer, the local LLM and the hybrid all
expose ``detect(text) -> list[Span]``. The evaluator, the hybrid fusion layer
and the API depend only on this interface.
"""

from __future__ import annotations

import inspect
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar

from privymed.schema import GOLD_SOURCE, Span, span_sort_key, validate_spans_against_text

# Titles and role words that precede a name but are not part of it (annotation guide).
# Shared by every detector that strips them (review M5-5: Presidio and the LLM mapping had
# two different lists). "\b" keeps names such as "Drew" or "Patience" intact.
_LEADING_TITLE = re.compile(
    r"(?:(?:patient|pt|name|dr|prof|mr|mrs|ms|miss|sister|nurse)\b\.?\s*)+", re.IGNORECASE
)


def strip_leading_title(text: str, start: int, end: int) -> int:
    """Return the new start of a name span after skipping leading titles / role words."""
    m = _LEADING_TITLE.match(text, start, end)
    return m.end() if m else start


_EDGE_PUNCT = ".,;:="  # "=" ends field labels ("MRN=...", guide) and never belongs to an entity


def trim_boundaries(text: str, start: int, end: int) -> tuple[int, int]:
    """Normalise a candidate span's edges to the annotation guide.

    Strips whitespace and ``.,;:`` at both ends. Parentheses are stripped only when
    unbalanced, so ``(042) 35761234`` keeps its "(" (guide: PHONE includes parentheses)
    while ``Khan)`` loses its ")". Shared by all rule-based detectors so their boundary
    conventions cannot drift apart (Milestone 3 review finding M3-2).
    """
    changed = True
    while changed and end > start:
        changed = False
        span = text[start:end]
        last, first = span[-1], span[0]
        if (
            last.isspace()
            or last in _EDGE_PUNCT
            or (last == ")" and span.count("(") < span.count(")"))
        ):
            end -= 1
            changed = True
        elif (
            first.isspace()
            or first in _EDGE_PUNCT
            or (first == "(" and span.count(")") < span.count("("))
        ):
            start += 1
            changed = True
    return start, end


class Detector(ABC):
    """Base class for all PII detectors.

    Concrete subclasses must define a non-empty class attribute ``name``;
    it is stamped onto every predicted span's ``source`` so fusion and
    per-system analysis can attribute each prediction.
    """

    name: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        name = getattr(cls, "name", None)
        if not isinstance(name, str) or not name or name == GOLD_SOURCE:
            raise TypeError(f"{cls.__name__} must define a non-empty `name` other than 'gold'")

    @abstractmethod
    def _detect(self, text: str) -> list[Span]:
        """Return predicted spans for ``text``. Implemented by subclasses."""

    def detect(self, text: str) -> list[Span]:
        """Detect spans, attribute them to this detector, check bounds, sort deterministically.

        Spans whose ``source`` is the default (``"gold"``) are re-labelled with
        ``self.name``; an explicit sub-source (e.g. ``"hybrid:regex"``) is kept.
        """
        spans = [
            s.model_copy(update={"source": self.name}) if s.source == GOLD_SOURCE else s
            for s in self._detect(text)
        ]
        validate_spans_against_text(text, spans)
        return sorted(spans, key=span_sort_key)

    def detect_batch(self, texts: Sequence[str]) -> list[list[Span]]:
        """Detect over many texts. Subclasses may override for true batching."""
        return [self.detect(t) for t in texts]
