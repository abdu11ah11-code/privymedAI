"""JSONL persistence for documents (one :class:`Document` per line, UTF-8)."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from privymed.schema import Document


def write_documents(path: Path, docs: Iterable[Document]) -> int:
    """Atomically write documents to ``path`` as JSONL. Returns the number written.

    Writes to a temporary sibling file and renames it into place, so a crash
    mid-generation never leaves a truncated-but-valid split behind.
    Duplicate ``doc_id`` values are rejected.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    seen: set[str] = set()
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            for doc in docs:
                if doc.doc_id in seen:
                    raise ValueError(f"duplicate doc_id: {doc.doc_id}")
                seen.add(doc.doc_id)
                fh.write(doc.model_dump_json())
                fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return len(seen)


def iter_documents(path: Path) -> Iterator[Document]:
    """Lazily read and validate documents from a JSONL file."""
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                doc = Document.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_no}: invalid document: {exc}") from exc
            if doc.doc_id in seen:
                raise ValueError(f"{path}:{line_no}: duplicate doc_id {doc.doc_id}")
            seen.add(doc.doc_id)
            yield doc


def read_documents(path: Path) -> list[Document]:
    return list(iter_documents(path))
