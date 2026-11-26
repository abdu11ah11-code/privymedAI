"""Template lint: render every family many times and check structural invariants."""

from __future__ import annotations

import re
from collections import Counter

import pytest

from privymed.data_generation.engine import TemplateFamily, generate_document
from privymed.data_generation.entities import EntityFactory
from privymed.data_generation.families import FAMILIES
from privymed.schema import Document, EntityType

RENDERS = 150


@pytest.fixture(scope="module")
def rendered() -> dict[str, list[Document]]:
    factory = EntityFactory(0)
    return {
        fam.family_id: [generate_document(fam, factory, 2024, i) for i in range(RENDERS)]
        for fam in FAMILIES
    }


def test_family_ids_unique() -> None:
    ids = [f.family_id for f in FAMILIES]
    assert len(ids) == len(set(ids))


def test_nine_doc_types_each_with_two_or_more_families() -> None:
    counts = Counter(f.doc_type for f in FAMILIES if not f.entity_free)
    assert len(counts) == 9
    assert min(counts.values()) >= 2


def test_entity_free_families_have_no_spans(rendered: dict[str, list[Document]]) -> None:
    free = [f for f in FAMILIES if f.entity_free]
    assert len(free) >= 2
    for fam in free:
        assert all(not d.spans for d in rendered[fam.family_id]), fam.family_id


def test_narrative_paragraphs_appear(rendered: dict[str, list[Document]]) -> None:
    docs = rendered["dis_formal"]
    assert any("clinic with the results" in d.text or "auscultation" in d.text for d in docs)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.family_id)
def test_no_template_artifacts(family: TemplateFamily, rendered: dict[str, list[Document]]) -> None:
    for doc in rendered[family.family_id]:
        for line in doc.text.split("\n"):
            assert line == line.rstrip(), f"trailing whitespace in {doc.doc_id}: {line!r}"
        assert not re.search(r"[{}]|\[\[|\]\]", doc.text), f"unrendered syntax in {doc.doc_id}"
        assert not re.search(r" [.,;:]", doc.text), f"space before punctuation in {doc.doc_id}"
        assert doc.text == doc.text.strip()
        assert 40 <= len(doc.text) <= 3000


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.family_id)
def test_family_produces_at_least_three_entity_types(
    family: TemplateFamily, rendered: dict[str, list[Document]]
) -> None:
    if family.entity_free:
        pytest.skip("entity-free family")
    labels = {s.label for doc in rendered[family.family_id] for s in doc.spans}
    assert len(labels) >= 3, f"{family.family_id} only produces {labels}"


def test_all_entity_types_covered(rendered: dict[str, list[Document]]) -> None:
    labels = {s.label for docs in rendered.values() for d in docs for s in d.spans}
    assert labels == set(EntityType)


def test_families_render_differently(rendered: dict[str, list[Document]]) -> None:
    for fid, docs in rendered.items():
        assert len({d.text for d in docs}) == RENDERS, f"{fid} produced duplicate documents"
