"""Span-level evaluation shared by every detection system (ADR-001)."""

from privymed.evaluation.metrics import (
    MODES,
    Counts,
    EvalResult,
    Mode,
    evaluate,
    leak_rate,
    match_document,
)

__all__ = ["MODES", "Counts", "EvalResult", "Mode", "evaluate", "leak_rate", "match_document"]
