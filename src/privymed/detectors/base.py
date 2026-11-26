"""The common interface every detection system implements.

Regex, Presidio, the fine-tuned transformer, the local LLM and the hybrid all
expose ``detect(text) -> list[Span]``. The evaluator, the hybrid fusion layer
and the API depend only on this interface.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar

from privymed.schema import GOLD_SOURCE, Span, span_sort_key, validate_spans_against_text


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
