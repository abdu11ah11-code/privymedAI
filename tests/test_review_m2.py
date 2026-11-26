"""Regression tests for the Milestone 2 independent review findings (M2-1 ... M2-13)."""

from __future__ import annotations

import random
import re
from collections import Counter

import pytest

from privymed.data_generation import pools
from privymed.data_generation.dataset import (
    DataConfig,
    SplitSizes,
    assign_splits,
    generate_split,
)
from privymed.data_generation.engine import NoteContext, generate_document
from privymed.data_generation.entities import EntityFactory, Value
from privymed.data_generation.families import FAMILIES, FAMILIES_BY_ID
from privymed.data_generation.noise import NoiseApplier, NoiseProfile
from privymed.schema import Document, EntityType, Span
from privymed.validation import find_duplicates, masked_text, title_stats, validate

CFG = DataConfig(
    version="t",
    seed=1,
    split_seed=7,
    pk_ratio=0.6,
    sizes=SplitSizes(train=1, dev=1, test_id=1),
    bundle_ratio=0.3,
)


@pytest.fixture(scope="module")
def assignment() -> dict[str, str]:
    return dict(assign_splits(FAMILIES, 7)[0])


@pytest.fixture(scope="module")
def splits(assignment: dict[str, str]) -> dict[str, list[Document]]:
    sizes = {"train": 600, "dev": 200, "test_id": 200}
    out: dict[str, list[Document]] = {}
    for split, n in sizes.items():
        members = [FAMILIES_BY_ID[f] for f, s in assignment.items() if s == split]
        out[split] = list(generate_split(split, members, n, CFG))  # type: ignore[arg-type]
    return out


# ------------------------------------------------------------------ M2-1 title shortcut
def test_staff_titles_vary_and_patients_can_be_doctors(splits: dict[str, list[Document]]) -> None:
    for split, docs in splits.items():
        t = title_stats(docs)
        assert t["STAFF_after_dr"] < 0.8, (split, t)  # was 0.70-1.00 before the fix
    all_docs = [d for docs in splits.values() for d in docs]
    assert title_stats(all_docs)["PATIENT_after_dr"] > 0.0  # was exactly 0 before the fix


# ------------------------------------------------------------------ M2-2 family leakage
def test_validator_catches_reviewer_simulated_family_leak(
    splits: dict[str, list[Document]], assignment: dict[str, str]
) -> None:
    """Reproduce the review's probe: inject fresh test-family docs into train."""
    clean = validate(splits, assignment)
    assert clean["errors"] == 0, clean["issues_by_check"]

    test_family = next(f for f, s in assignment.items() if s == "test_id" and f == "rx_label")
    leaked = [
        generate_document(FAMILIES_BY_ID[test_family], EntityFactory(99), 99, i) for i in range(50)
    ]
    report = validate({**splits, "train": splits["train"] + leaked}, assignment)
    checks = report["issues_by_check"]
    assert isinstance(checks, dict)
    assert checks.get("error:family_leak") == 50
    # Even without metadata, the masked-template check sees the shared structure.
    assert "error:structural_dup_cross" in checks


def test_masked_text_replaces_spans() -> None:
    doc = Document(
        doc_id="d",
        text="Pt Ali Khan MRN 12345",
        spans=(
            Span(start=3, end=11, label=EntityType.PATIENT),
            Span(start=16, end=21, label=EntityType.ID),
        ),
    )
    assert masked_text(doc) == "Pt <PATIENT> MRN <ID>"


# ------------------------------------------------------------------ M2-9 id collisions
def test_doc_id_collision_is_reported_not_crashing() -> None:
    a = Document(doc_id="same", text="alpha beta gamma delta epsilon zeta")
    b = Document(doc_id="same", text="one two three four five six seven")
    rep = find_duplicates({"train": [a], "dev": [b]})
    assert rep.doc_id_collisions == 1


# ------------------------------------------------------------------ M2-6/7 pools
def test_building_words_disjoint_from_hospital_cores() -> None:
    cores = {c.lower() for c in pools.HOSPITAL_CORES}
    for word in pools.PK_BUILDING_WORDS:
        assert not any(word.lower() in c or c in word.lower() for c in cores), word


def test_eval_splits_get_several_name_word_negatives() -> None:
    from privymed.data_generation.dataset import _is_name_word_negative, split_pools

    for split, pool in split_pools(7).items():
        hard = [s for s in pool["narrative"] if _is_name_word_negative(s)]
        assert len(hard) >= 4, (split, hard)
        assert len(pool["hospital_cores"]) >= 9, split


# ------------------------------------------------------------------ M2-10 bundles
def test_new_part_redraws_fillers_but_keeps_cast() -> None:
    """Review M2-10: cached fillers ({narrative1}, {medication}) were reused across bundle parts.

    Chance sentence repeats across parts are expected (~18 draws from a 47-sentence pool);
    what must not happen is the *same cached filler value* being reused.
    """
    f = EntityFactory(4)
    differs = 0
    for i in range(200):
        f.reseed(i)
        ctx = NoteContext(f)
        name = ctx.resolve("patient.name", "full")
        first = (ctx.resolve("narrative1"), ctx.resolve("medication"))
        ctx.new_part()
        second = (ctx.resolve("narrative1"), ctx.resolve("medication"))
        assert ctx.resolve("patient.name", "full") == name  # cast is kept
        differs += first != second
    assert differs >= 190  # redrawn (identical only by chance)


# ------------------------------------------------------------------ M2-12 unlabelled PII
_UNLABELLED_PII = {
    "long digit run": re.compile(r"\d{7,}"),
    "PK mobile shape": re.compile(r"(\+92|\b0)3\d\d[- ]?\d{3}[- ]?\d{4}"),
    "CNIC shape": re.compile(r"\b\d{5}-\d{7}-\d\b"),
    "email": re.compile(r"@"),
    "4-digit year": re.compile(r"\b(19|20)\d\d\b"),
}


def test_no_unlabelled_pii_shapes(splits: dict[str, list[Document]]) -> None:
    """With every gold span masked, no PII-shaped text may remain (missing-label check)."""
    for docs in splits.values():
        for d in docs:
            masked = masked_text(d)
            for name, pattern in _UNLABELLED_PII.items():
                assert not pattern.search(masked), f"{d.doc_id}: unlabelled {name}"


# ------------------------------------------------------------------ M2-13 case tag
def test_case_noise_is_tagged_on_entities() -> None:
    applier = NoiseApplier(NoiseProfile("u", 0.0, 0.0, "upper"), random.Random(0))
    v = applier.entity(Value("Ali Khan", EntityType.PATIENT, "full"))
    assert v.text == "ALI KHAN" and v.fmt == "full+case"


# ------------------------------------------------------------------ M2-4 balance
def test_every_split_meets_min_type_share(splits: dict[str, list[Document]]) -> None:
    for split, docs in splits.items():
        c = Counter(s.label for d in docs for s in d.spans)
        total = sum(c.values())
        assert min(c[t] / total for t in EntityType) >= 0.015, (split, c)
