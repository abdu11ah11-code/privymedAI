"""Character spans <-> subword BIO labels, independent of any particular tokenizer.

Works from the ``offset_mapping`` a fast Hugging Face tokenizer returns: one
``(start, end)`` character interval per subword token, ``(0, 0)`` for special
tokens.

Labelling scheme ("label all subwords"):
    * the first subword of a span gets ``B-<TYPE>``, the following ones ``I-<TYPE>``;
    * subwords outside every span get ``O``;
    * special tokens get ``IGNORE`` (-100), which the cross-entropy loss skips.

Labelling every subword (instead of only the first subword of each word) lets the
predictions be decoded straight back into character spans without a word
tokenizer, and keeps the scheme identical across tokenizers whose word splitting
differs (WordPiece, BPE, SentencePiece).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from privymed.detectors.base import trim_boundaries
from privymed.schema import EntityType, Span

IGNORE = -100
LABELS: tuple[str, ...] = (
    "O",
    *(f"{prefix}-{t.value}" for t in EntityType for prefix in ("B", "I")),
)
LABEL2ID: dict[str, int] = {label: i for i, label in enumerate(LABELS)}
ID2LABEL: dict[int, str] = dict(enumerate(LABELS))

Offset = tuple[int, int]


@dataclass(frozen=True)
class AlignmentStats:
    tokens: int = 0
    entity_tokens: int = 0
    straddling: int = 0  # subwords that cross a span boundary and cannot be represented
    merged_prefix: int = 0  # tokens that glue outside chars to a span start, e.g. BPE "(+"
    unlabelled_spans: int = 0  # spans that no subword starts inside (should be 0)


def _is_special(offset: Offset) -> bool:
    return offset[0] == offset[1]


def clean_offsets(text: str, offsets: Sequence[Offset]) -> list[Offset]:
    """Trim whitespace from each subword's character range.

    SentencePiece tokenizers (DeBERTa-v3) report the leading space as part of a token:
    "▁Khan" -> (9, 14) where text[9] == " ". Without trimming, every word-initial
    entity token appears to start before its span (measured on train: 39,572
    straddling tokens and 2,770 unlabelled spans for deberta-v3-base). Special tokens
    and pure-whitespace tokens become (0, 0) and are ignored.
    """
    out: list[Offset] = []
    for start, end in offsets:
        if start == end:
            out.append((0, 0))
            continue
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        out.append((start, end) if end > start else (0, 0))
    return out


def _prefix_trims_away(text: str | None, token_start: int, span: Span) -> bool:
    """True if decoding would trim the characters a token glues before ``span.start``.

    Without the text we cannot check, so we assume yes (offset-only callers, tests).
    """
    if text is None:
        return True
    start, end = trim_boundaries(text, token_start, span.end)
    return (start, end) == (span.start, span.end)


def spans_to_labels(
    offsets: Sequence[Offset], spans: Sequence[Span], text: str | None = None
) -> tuple[list[int], AlignmentStats]:
    """Label each subword from gold character spans.

    A subword that straddles a span boundary is labelled with the span it starts
    in (or ``O``) and counted in ``AlignmentStats.straddling``, so alignment
    quality is measured rather than assumed.
    """
    ordered = sorted(spans, key=lambda s: s.start)
    labels = [IGNORE] * len(offsets)
    straddling = entity_tokens = merged = 0
    first_token_seen = [False] * len(ordered)
    si = 0
    for ti, (start, end) in enumerate(offsets):
        if _is_special((start, end)):
            continue
        while si < len(ordered) and ordered[si].end <= start:
            si += 1
        label = "O"
        if si < len(ordered):
            span = ordered[si]
            if span.start <= start < span.end:
                prefix = "I" if first_token_seen[si] else "B"
                first_token_seen[si] = True
                label = f"{prefix}-{span.label.value}"
                entity_tokens += 1
                if end > span.end:
                    straddling += 1
            elif start < span.start < end and _prefix_trims_away(text, start, span):
                # Token glues outside characters to the span start (RoBERTa byte-level BPE:
                # "(+", "(#", "=(", "=#"). Label it as the span's first token; decoding trims
                # the excluded leading "(" / "=" again (review M4-1: labelling it O taught the
                # model to drop the "+" / "#" and made 322 train spans unrepresentable).
                first_token_seen[si] = True
                label = f"B-{span.label.value}"
                entity_tokens += 1
                merged += 1
                if end > span.end:
                    straddling += 1
            elif start < span.start < end:
                straddling += 1  # glued prefix would not trim away (e.g. "MRN12"): unrepresentable
        labels[ti] = LABEL2ID[label]
    stats = AlignmentStats(
        tokens=sum(1 for o in offsets if not _is_special(o)),
        entity_tokens=entity_tokens,
        straddling=straddling,
        merged_prefix=merged,
        unlabelled_spans=sum(1 for seen in first_token_seen if not seen),
    )
    return labels, stats


def labels_to_spans(
    offsets: Sequence[Offset],
    label_ids: Sequence[int],
    scores: Sequence[float] | None = None,
    source: str = "transformer",
    text: str | None = None,
) -> list[Span]:
    """Decode per-subword label ids into character spans.

    ``B-X`` starts a span; ``I-X`` continues an open ``X`` span or, if none is open,
    starts one (lenient decoding). The span covers the first to the last subword's
    characters. ``scores`` (per-subword probability of the predicted label) are
    averaged into the span score.
    """
    spans: list[Span] = []
    cur_label: str | None = None
    cur_start = cur_end = 0
    cur_scores: list[float] = []

    def close() -> None:
        if cur_label is not None:
            score = sum(cur_scores) / len(cur_scores) if cur_scores else 1.0
            start, end = cur_start, cur_end
            if text is not None:  # trim chars a merged-prefix token glued on, per the guide
                start, end = trim_boundaries(text, start, end)
            if end <= start:
                return
            spans.append(
                Span(
                    start=start,
                    end=end,
                    label=EntityType(cur_label),
                    score=min(1.0, max(0.0, score)),
                    source=source,
                )
            )

    for i, ((start, end), lid) in enumerate(zip(offsets, label_ids, strict=True)):
        if _is_special((start, end)) or lid == IGNORE:
            continue
        tag = ID2LABEL[int(lid)]
        prefix, _, label = tag.partition("-")
        score = float(scores[i]) if scores is not None else 1.0
        if tag == "O":
            close()
            cur_label = None
            cur_scores = []
        elif prefix == "B" or label != cur_label:
            close()
            cur_label, cur_start, cur_end, cur_scores = label, start, end, [score]
        else:
            cur_end = end
            cur_scores.append(score)
    close()
    return spans
