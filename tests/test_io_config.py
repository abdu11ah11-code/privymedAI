from __future__ import annotations

import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from privymed.config import load_config
from privymed.io import read_documents, write_documents
from privymed.repro import set_global_seed
from privymed.schema import Document, EntityType, Span

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_jsonl_roundtrip(tmp_path: Path) -> None:
    docs = [
        Document(
            doc_id="a",
            text="Call 0300-1234567",
            spans=(Span(start=5, end=17, label=EntityType.PHONE),),
        ),
        Document(doc_id="b", text="No PII here."),
    ]
    path = tmp_path / "nested" / "docs.jsonl"
    assert write_documents(path, docs) == 2
    assert read_documents(path) == docs


def test_jsonl_reports_line_number_on_bad_record(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"doc_id": "a", "text": "x"}\n{"doc_id": ""}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.jsonl:2"):
        read_documents(path)


def test_default_config_loads_with_repo_relative_paths() -> None:
    cfg = load_config(REPO_ROOT / "configs" / "default.yaml")
    assert cfg.seed == 42
    assert cfg.paths.data_dir == REPO_ROOT / "data"


def test_config_rejects_seed_numpy_cannot_use(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(f"seed: {2**32}\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_config_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_config(path)


def test_jsonl_write_is_atomic_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "docs.jsonl"
    write_documents(path, [Document(doc_id="old", text="x")])

    def bad_stream() -> Iterator[Document]:
        yield Document(doc_id="new", text="y")
        raise RuntimeError("generator crashed")

    with pytest.raises(RuntimeError):
        write_documents(path, bad_stream())
    assert [d.doc_id for d in read_documents(path)] == ["old"]
    assert not list(tmp_path.glob("*.tmp"))


def test_jsonl_rejects_duplicate_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        write_documents(tmp_path / "d.jsonl", [Document(doc_id="a", text="x")] * 2)


def test_jsonl_preserves_unicode_and_inner_newlines(tmp_path: Path) -> None:
    doc = Document(doc_id="u", text="Mr. Ali Raza\r\nمریض\nDOB: 01/02/1990")
    path = tmp_path / "u.jsonl"
    write_documents(path, [doc])
    assert read_documents(path) == [doc]


def test_config_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("seed: 1\nsede: 2\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_seed_makes_python_random_reproducible() -> None:
    set_global_seed(123)
    first = [random.random() for _ in range(3)]
    set_global_seed(123)
    assert [random.random() for _ in range(3)] == first
