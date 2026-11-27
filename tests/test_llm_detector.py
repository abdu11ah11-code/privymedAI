"""LLM prompt construction and detector behaviour with a fake Ollama response."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from privymed.config import find_repo_root
from privymed.detectors.llm import LLMDetector
from privymed.io import read_documents
from privymed.llm.prompt import (
    INSTRUCTIONS,
    build_messages,
    gold_answer,
    prompt_fingerprint,
    select_examples,
)
from privymed.schema import Document, EntityType, Span

ROOT = find_repo_root()
TRAIN = ROOT / "data/synthetic/v1/train.jsonl"
needs_data = pytest.mark.skipif(not TRAIN.is_file(), reason="dataset v1 not generated")


def _doc(doc_id: str, text: str, *spans: tuple[int, int, EntityType]) -> Document:
    return Document(
        doc_id=doc_id,
        text=text,
        spans=tuple(Span(start=a, end=b, label=lab) for a, b, lab in spans),
    )


def test_gold_answer_lists_distinct_mentions_once() -> None:
    doc = _doc(
        "d",
        "Ali saw Ali at CMC",
        (0, 3, EntityType.PATIENT),
        (8, 11, EntityType.PATIENT),
        (15, 18, EntityType.HOSPITAL),
    )
    assert json.loads(gold_answer(doc)) == {
        "entities": [{"text": "Ali", "type": "PATIENT"}, {"text": "CMC", "type": "HOSPITAL"}]
    }


@needs_data
def test_examples_come_from_train_and_are_deterministic() -> None:
    train = read_documents(TRAIN)
    a, b = select_examples(train), select_examples(train)
    assert [d.doc_id for d in a] == [d.doc_id for d in b] and len(a) == 3
    train_ids = {d.doc_id for d in train}
    assert all(d.doc_id in train_ids and d.metadata["split"] == "train" for d in a)
    covered = {s.label for d in a for s in d.spans}
    assert len(covered) >= 6  # greedy cover reaches most types


@needs_data
def test_prompt_examples_are_not_dev_documents() -> None:
    # The test split is never opened here (CLAUDE.md rule 3); examples come from train by
    # construction, and dev — the tuning split — must not leak into the prompt either.
    train = read_documents(TRAIN)
    examples = select_examples(train)
    prompt = "\n".join(m["content"] for m in build_messages(examples, "<NOTE>"))
    dev_ids = {d.doc_id for d in read_documents(Path(ROOT / "data/synthetic/v1/dev.jsonl"))}
    example_ids = prompt_fingerprint(examples)["example_doc_ids"]
    assert isinstance(example_ids, list) and not set(example_ids) & dev_ids
    assert INSTRUCTIONS in prompt and prompt.endswith("<NOTE>")


@needs_data
def test_detector_maps_fake_response_and_counts_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    det = LLMDetector()
    reply = {
        "entities": [
            {"text": "Ayesha Khan", "type": "PATIENT"},
            {"text": "Imran", "type": "STAFF"},
            {"text": "Nobody", "type": "PATIENT"},  # hallucination
        ]
    }
    monkeypatch.setattr(det, "_chat", lambda text: json.dumps(reply))
    text = "Patient Ayesha Khan seen by Dr. Imran."
    spans = det.detect(text)
    assert [(text[s.start : s.end], s.label) for s in spans] == [
        ("Ayesha Khan", EntityType.PATIENT),
        ("Imran", EntityType.STAFF),
    ]
    assert det.stats.hallucinated == 1 and det.stats.documents == 1
    assert all(s.source == "llm" for s in spans)


@needs_data
def test_detector_counts_parse_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    det = LLMDetector()
    monkeypatch.setattr(det, "_chat", lambda text: "Sure! Here are the entities: Ayesha")
    assert det.detect("Ayesha") == [] and det.stats.parse_failures == 1
