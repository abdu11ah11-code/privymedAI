"""Span <-> BIO conversion over a simple, offset-preserving word tokenizer.

Used for (a) dataset validation — every gold span must align to token
boundaries, otherwise BIO training would silently drop or distort labels —
and (b) seqeval cross-checks of the span evaluator.

The transformer pipeline (Milestone 4) aligns spans to *subword* offsets from
its own tokenizer; this module defines the word-level reference.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise

from privymed.schema import EntityType, Span

_TOKEN = re.compile(r"\w+|[^\w\s]")

Token = tuple[int, int]  # [start, end) character offsets


class AlignmentError(ValueError):
    """A span boundary falls inside a token."""


def tokenize(text: str) -> list[Token]:
    """Word tokens: runs of word characters, or single punctuation characters."""
    return [m.span() for m in _TOKEN.finditer(text)]


def spans_to_bio(tokens: Sequence[Token], spans: Sequence[Span]) -> list[str]:
    """Tag tokens with B-/I-/O. Raises :class:`AlignmentError` on mid-token boundaries."""
    tags = ["O"] * len(tokens)
    ordered = sorted(spans, key=lambda s: s.start)
    for a, b in pairwise(ordered):
        if a.overlaps(b):  # BIO cannot represent overlaps; never overwrite silently
            raise AlignmentError(f"overlapping spans {a.start}:{a.end} and {b.start}:{b.end}")
    ti = 0
    for span in ordered:
        while ti < len(tokens) and tokens[ti][1] <= span.start:
            ti += 1
        first = True
        j = ti
        while j < len(tokens) and tokens[j][0] < span.end:
            t_start, t_end = tokens[j]
            if t_start < span.start or t_end > span.end:
                raise AlignmentError(f"span {span.start}:{span.end} cuts token {t_start}:{t_end}")
            tags[j] = f"{'B' if first else 'I'}-{span.label.value}"
            first = False
            j += 1
        if first:
            raise AlignmentError(f"span {span.start}:{span.end} covers no token")
    return tags


def bio_to_spans(tokens: Sequence[Token], tags: Sequence[str], source: str = "bio") -> list[Span]:
    """Decode BIO tags into spans. A stray ``I-X`` (no open ``X``) starts a new span."""
    if len(tokens) != len(tags):
        raise ValueError("tokens and tags differ in length")
    spans: list[Span] = []
    open_label: str | None = None
    start = end = 0

    def close() -> None:
        if open_label is not None:
            spans.append(Span(start=start, end=end, label=EntityType(open_label), source=source))

    for (t_start, t_end), tag in zip(tokens, tags, strict=True):
        prefix, _, label = tag.partition("-")
        if tag == "O":
            close()
            open_label = None
        elif prefix == "B" or (prefix == "I" and label != open_label):
            close()
            open_label, start, end = label, t_start, t_end
        elif prefix == "I":
            end = t_end
        else:
            raise ValueError(f"invalid BIO tag {tag!r}")
    close()
    return spans
