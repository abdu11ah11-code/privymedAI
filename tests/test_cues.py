"""Leak lint (review finding M3-1): every rule cue must occur in train or dev text.

A cue that occurs only in test-split templates would fit the rules to test documents.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from privymed.config import find_repo_root
from privymed.detectors.cues import ALL_CUES, alternation, cue_pattern
from privymed.io import read_documents

ROOT = find_repo_root()
DEV_SPLITS = [ROOT / "data/synthetic/v1/train.jsonl", ROOT / "data/synthetic/v1/dev.jsonl"]


@pytest.fixture(scope="module")
def train_dev_text() -> str:
    if not all(p.is_file() for p in DEV_SPLITS):
        pytest.skip("dataset v1 not generated (run privymed-generate)")
    return "\n".join(d.text for p in DEV_SPLITS for d in read_documents(Path(p)))


@pytest.mark.parametrize("cue", ALL_CUES)
def test_every_cue_occurs_in_train_or_dev(cue: str, train_dev_text: str) -> None:
    pattern = re.compile(rf"(?<![\w#]){cue_pattern(cue)}(?!\w)", re.IGNORECASE)
    assert pattern.search(train_dev_text), f"cue {cue!r} not in train/dev: possible test leak"


@pytest.mark.parametrize(
    "removed", ["Prescriber", "Rx No", "Lab No", "Booking reference", "Booked for", "Reg No"]
)
def test_leaked_cues_are_gone(removed: str) -> None:
    assert removed not in ALL_CUES


def test_alternation_prefers_longest_cue() -> None:
    m = re.match(alternation(["Patient", "Patient name"]), "Patient name: X")
    assert m is not None and m.group(0) == "Patient name"
