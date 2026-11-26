from __future__ import annotations

import pytest

from privymed.data_generation import pools
from privymed.data_generation.dataset import SPLITS, partition_pool, split_pools
from privymed.schema import Document, EntityType, Span
from privymed.validation import (
    check_document,
    find_duplicates,
    identifier_overlap,
    shape_violation,
    unseen_formats,
    validate,
)


def _doc(doc_id: str, text: str, *spans: tuple[int, int, EntityType], fmt: str = "x") -> Document:
    return Document(
        doc_id=doc_id,
        text=text,
        spans=tuple(Span(start=a, end=b, label=lab, fmt=fmt) for a, b, lab in spans),
    )


# ------------------------------------------------------------------ shape rules
@pytest.mark.parametrize(
    ("label", "surface", "ok"),
    [
        (EntityType.CNIC, "35202-1234567-1", True),
        (EntityType.CNIC, "35202-123456-1", False),
        (EntityType.EMAIL, "a.b@x.com", True),
        (EntityType.EMAIL, "a.b at x.com", False),
        (EntityType.PHONE, "+92 300 1234567", True),
        (EntityType.PHONE, "12345", False),
        (EntityType.PATIENT, "Ayesha Khan", True),
        (EntityType.PATIENT, "Ayesha 2", False),
        (EntityType.DATE, "12 March", True),
        (EntityType.DATE, "yesterday", False),
        (EntityType.ID, "MRN-001", True),
        (EntityType.ID, "MRN", False),
    ],
)
def test_shape_rules(label: EntityType, surface: str, ok: bool) -> None:
    assert (shape_violation(label, surface) is None) is ok


def test_check_document_flags_shape_and_alignment() -> None:
    bad_shape = _doc("a", "CNIC 123", (5, 8, EntityType.CNIC))
    assert [i.check for i in check_document(bad_shape)] == ["shape"]
    misaligned = _doc("b", "MRN12345", (3, 8, EntityType.ID))
    assert [i.check for i in check_document(misaligned)] == ["bio_alignment"]
    assert check_document(_doc("c", "Pt Ali Khan", (3, 11, EntityType.PATIENT))) == []


# ------------------------------------------------------------------ duplicates
def test_exact_and_near_duplicates_across_and_within_splits() -> None:
    base = " ".join(f"word{i}" for i in range(60))
    near = base.replace("word59", "changed")  # 1 of 56 shingles differs -> J ~ 0.96
    other = " ".join(f"other{i}" for i in range(60))
    rep = find_duplicates(
        {
            "train": [_doc("t1", base), _doc("t2", other)],
            "test_id": [_doc("x1", base), _doc("x2", near)],
        }
    )
    assert rep.exact_cross == 1
    assert rep.near_cross >= 2  # x1~t1 (exact, also near) and x2~t1
    assert rep.near_within.get("test_id") == 1  # x1~x2


def test_validate_reports_cross_split_dup_as_error() -> None:
    text = "Patient seen today with no complaints at all in clinic."
    report = validate({"train": [_doc("a", text)], "dev": [_doc("b", text)]})
    errors, by_check = report["errors"], report["issues_by_check"]
    assert isinstance(errors, int) and errors >= 1
    assert isinstance(by_check, dict) and "error:exact_dup_cross" in by_check


# ------------------------------------------------------------------ leakage
def test_identifier_overlap_share() -> None:
    train = [_doc("t", "Ali Khan", (0, 8, EntityType.PATIENT))]
    test = [
        _doc("a", "ali khan", (0, 8, EntityType.PATIENT)),
        _doc("b", "Sara Malik", (0, 10, EntityType.PATIENT)),
    ]
    ov = identifier_overlap(train, test)["PATIENT"]
    assert ov == {"distinct": 2, "seen_in_train": 1, "share": 0.5}


def test_unseen_formats_ignores_typo_suffix() -> None:
    train = [_doc("t", "01/02/2020", (0, 10, EntityType.DATE), fmt="dmy_slash")]
    test = [
        _doc("a", "01/02/2020", (0, 10, EntityType.DATE), fmt="dmy_slash+typo"),
        _doc("b", "2020-02-01", (0, 10, EntityType.DATE), fmt="iso"),
    ]
    assert unseen_formats(train, test) == {"DATE": ["iso"]}


# ------------------------------------------------------------------ split pools
def test_partition_pool_is_disjoint_complete_and_deterministic() -> None:
    parts = partition_pool(pools.HOSPITAL_CORES, 7, "hospital_cores")
    flat = [x for s in SPLITS for x in parts[s]]
    assert sorted(flat) == sorted(pools.HOSPITAL_CORES)
    assert len(set(flat)) == len(flat)
    assert parts == partition_pool(pools.HOSPITAL_CORES, 7, "hospital_cores")
    assert all(parts[s] for s in SPLITS)


def test_partition_pool_rejects_tiny_pool() -> None:
    with pytest.raises(ValueError):
        partition_pool(["a", "b"], 0, "tiny")


def test_every_split_gets_name_word_negatives_and_enough_sentences() -> None:
    sp = split_pools(7)
    name_words = (
        "Frank",
        "Bell",
        "Wood",
        "Will",
        "May",
        "White",
        "Rose",
        "Young",
        "Green",
        "Black",
    )
    for split in SPLITS:
        narrative = sp[split]["narrative"]
        assert len(narrative) >= 4
        assert any(s.split()[0].removesuffix("'s") in name_words for s in narrative), split
    all_sentences = [s for split in SPLITS for s in sp[split]["narrative"]]
    assert len(all_sentences) == len(set(all_sentences)) == len(pools.NARRATIVE)
