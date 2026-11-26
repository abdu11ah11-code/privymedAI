"""Offset-safe text noise: typos and case transforms.

Noise is applied to each piece of text *before* it is appended to the
:class:`~privymed.data_generation.engine.TextBuilder`, so span offsets are
computed on the noisy text and stay exact.

Invariants (tested):
* typo operations touch only ASCII letters strictly inside a word of >= 4
  letters, so the first and last character of every word — and therefore of
  every entity — are unchanged, and punctuation/whitespace never move;
* case transforms are skipped for any piece whose length would change
  (e.g. ``"ß".upper() == "SS"``).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Literal

from privymed.data_generation.entities import Value

Case = Literal["none", "upper", "lower"]
_WORD = re.compile(r"[A-Za-z]{4,}")


@dataclass(frozen=True, slots=True)
class NoiseProfile:
    name: str
    word_typo_rate: float  # probability that an eligible literal word gets one typo
    entity_typo_rate: float  # probability that an entity value gets one typo
    case: Case = "none"


CLEAN = NoiseProfile("clean", 0.0, 0.0)
PROFILES: tuple[tuple[NoiseProfile, float], ...] = (
    (CLEAN, 0.70),
    (NoiseProfile("light", 0.01, 0.0), 0.18),
    (NoiseProfile("heavy", 0.03, 0.05), 0.07),
    (NoiseProfile("upper", 0.01, 0.0, "upper"), 0.03),
    (NoiseProfile("lower", 0.01, 0.0, "lower"), 0.02),
)


def choose_profile(rng: random.Random) -> NoiseProfile:
    profiles = [p for p, _ in PROFILES]
    weights = [w for _, w in PROFILES]
    return rng.choices(profiles, weights=weights)[0]


def typo_word(word: str, rng: random.Random) -> str:
    """Apply one swap/drop/duplicate strictly inside ``word`` (len >= 4)."""
    if len(word) < 4:
        return word
    op = rng.choice(("swap", "drop", "dup"))
    if op == "swap":
        i = rng.randint(1, len(word) - 3)  # swap i, i+1; both interior
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    i = rng.randint(1, len(word) - 2)
    if op == "drop":
        return word[:i] + word[i + 1 :]
    return word[:i] + word[i] + word[i:]


def _apply_case(text: str, case: Case) -> str:
    if case == "none":
        return text
    out = text.upper() if case == "upper" else text.lower()
    return out if len(out) == len(text) else text


class NoiseApplier:
    """Applies one :class:`NoiseProfile` to literal text and entity values."""

    def __init__(self, profile: NoiseProfile, rng: random.Random) -> None:
        self.profile = profile
        self.rng = rng

    def literal(self, text: str) -> str:
        rate = self.profile.word_typo_rate
        if rate > 0:
            text = _WORD.sub(
                lambda m: (
                    typo_word(m.group(0), self.rng) if self.rng.random() < rate else m.group(0)
                ),
                text,
            )
        return _apply_case(text, self.profile.case)

    def entity(self, value: Value) -> Value:
        text, fmt = value.text, value.fmt
        rate = self.profile.entity_typo_rate
        if rate > 0 and self.rng.random() < rate:
            words = list(_WORD.finditer(text))
            if words:
                m = self.rng.choice(words)
                text = text[: m.start()] + typo_word(m.group(0), self.rng) + text[m.end() :]
                fmt = f"{fmt}+typo"
        cased = _apply_case(text, self.profile.case)
        if cased != text:
            fmt = f"{fmt}+case"
        return Value(cased, value.label, fmt)
