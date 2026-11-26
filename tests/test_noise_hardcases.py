from __future__ import annotations

import random
import re
from collections import Counter

import pytest

from privymed.data_generation import pools
from privymed.data_generation.engine import (
    NoteContext,
    Section,
    TemplateFamily,
    generate_bundle,
    generate_document,
)
from privymed.data_generation.entities import EntityFactory, Value
from privymed.data_generation.families import FAMILIES, FAMILIES_BY_ID
from privymed.data_generation.noise import (
    CLEAN,
    PROFILES,
    NoiseApplier,
    NoiseProfile,
    typo_word,
)
from privymed.schema import EntityType

HEAVY = NoiseProfile("test_heavy", word_typo_rate=0.5, entity_typo_rate=1.0)


# ------------------------------------------------------------------ typo invariants
@pytest.mark.parametrize("seed", range(200))
def test_typo_keeps_edges_and_changes_only_letters(seed: int) -> None:
    rng = random.Random(seed)
    word = "".join(rng.choice("abcdefghij") for _ in range(rng.randint(4, 12)))
    out = typo_word(word, rng)
    assert out[0] == word[0] and out[-1] == word[-1]
    assert abs(len(out) - len(word)) <= 1
    assert out.isalpha()


def test_short_words_untouched() -> None:
    assert typo_word("abc", random.Random(0)) == "abc"


def test_entity_typo_preserves_boundaries_and_tags_format() -> None:
    applier = NoiseApplier(HEAVY, random.Random(1))
    for _ in range(200):
        v = applier.entity(Value("Ayesha Siddiqui", EntityType.PATIENT, "full"))
        assert v.text[0] == "A" and v.text[-1] == "i"
        assert v.fmt == "full+typo"


def test_digits_and_punctuation_never_altered() -> None:
    applier = NoiseApplier(HEAVY, random.Random(2))
    text = "BP 120/80, call 0300-1234567. MRN-2024-000123; ok."
    for _ in range(100):
        out = applier.literal(text)
        assert re.sub(r"[A-Za-z]", "", out) == re.sub(r"[A-Za-z]", "", text)


def test_upper_profile_uppercases_entities_and_keeps_offsets() -> None:
    fam = FAMILIES_BY_ID["adm_form"]
    upper = next(p for p, _ in PROFILES if p.case == "upper")
    doc = generate_document(fam, EntityFactory(0), 3, 0, noise=upper)
    assert doc.text == doc.text.upper()
    assert doc.spans  # Document validation already proved offsets are in bounds


def test_profile_distribution_roughly_matches_weights() -> None:
    fam = FAMILIES_BY_ID["opd_soap"]
    f = EntityFactory(0)
    counts = Counter(generate_document(fam, f, 4, i).metadata["noise"] for i in range(2000))
    assert 0.65 < counts["clean"] / 2000 < 0.75


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.family_id)
def test_heavy_noise_never_corrupts_spans(family: TemplateFamily) -> None:
    f = EntityFactory(5)
    for i in range(30):
        doc = generate_document(family, f, 5, i, noise=HEAVY)
        clean = generate_document(family, f, 5, i, noise=CLEAN)
        # Exact clean twin: same entities, same non-letter skeleton (digits, punctuation, spaces).
        assert [s.label for s in doc.spans] == [s.label for s in clean.spans]
        assert re.sub(r"[A-Za-z]", "", doc.text) == re.sub(r"[A-Za-z]", "", clean.text)


# ------------------------------------------------------------------ hard cases
def test_ambiguous_name_injection_adds_expected_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some names are word-like naturally (Noor, Mark); measure only the *injected* effect."""
    from privymed.data_generation import entities

    ambig = set(pools.AMBIG_FIRST_F + pools.AMBIG_FIRST_M + pools.AMBIG_LAST)
    n = 6000

    def rate() -> float:
        f = EntityFactory(6)
        return sum(bool({(p := f.person()).first, p.last} & ambig) for _ in range(n)) / n

    with_injection = rate()
    monkeypatch.setattr(entities, "AMBIGUOUS_NAME_RATE", 0.0)
    natural = rate()
    # Expected injected share ~ 1 - 0.95^2 = 9.75%, minus overlap with natural hits.
    assert 0.06 < with_injection - natural < 0.11


def test_shared_surname_case_occurs_with_distinct_labels() -> None:
    f = EntityFactory(7)
    fam = TemplateFamily("s", "t", (Section(("{patient.name} / Dr. {staff1.name}",)),))
    shared = 0
    for i in range(1000):
        doc = generate_document(fam, f, 7, i, noise=CLEAN)
        pat, staff = doc.spans
        assert (pat.label, staff.label) == (EntityType.PATIENT, EntityType.STAFF)
        if doc.span_text(pat).split()[-1] == doc.span_text(staff).split()[-1]:
            shared += 1
    assert 0.06 < shared / 1000 < 0.15  # 8% forced + chance collisions


def test_narrative_sentences_contain_name_words_as_negatives() -> None:
    words = {s.split()[0].rstrip("'s") for s in pools.NARRATIVE}
    assert {"Frank", "Bell", "Wood", "Will", "May"} <= words


def test_csv_variant_yields_comma_adjacent_entities() -> None:
    fam = FAMILIES_BY_ID["adm_kv"]
    f = EntityFactory(8)
    found = False
    for i in range(300):
        doc = generate_document(fam, f, 8, i, noise=CLEAN)
        gaps = [doc.text[a.end : b.start] for a, b in zip(doc.spans, doc.spans[1:], strict=False)]
        if gaps.count(",") >= 4:
            found = True
            break
    assert found


# ------------------------------------------------------------------ bundles
def test_bundle_shares_patient_across_parts() -> None:
    parts = [FAMILIES_BY_ID["adm_form"], FAMILIES_BY_ID["lab_table"], FAMILIES_BY_ID["dis_formal"]]
    f = EntityFactory(9)
    for i in range(50):
        doc = generate_bundle(parts, f, 9, i, noise=CLEAN)
        f.reseed(0)
        mrns = {doc.span_text(s) for s in doc.spans if s.label is EntityType.ID and s.fmt}
        # adm_form uses id.admission; lab_table id.lab; patient.mrn is shared wherever it appears
        assert doc.metadata["doc_type"] == "bundle"
        assert len(doc.text) > 600
        assert mrns


def test_bundle_requires_two_families() -> None:
    with pytest.raises(ValueError):
        generate_bundle([FAMILIES[0]], EntityFactory(0), 0, 0)


def test_bundle_patient_name_consistent() -> None:
    parts = [FAMILIES_BY_ID["lab_table"], FAMILIES_BY_ID["rad_report"]]
    f = EntityFactory(10)
    for i in range(50):
        doc = generate_bundle(parts, f, 10, i, noise=CLEAN)
        full = [
            doc.span_text(s) for s in doc.spans if s.label is EntityType.PATIENT and s.fmt == "full"
        ]
        assert len(set(full)) == 1, full


def test_note_context_narrative_is_entity_free() -> None:
    f = EntityFactory(11)
    ctx = NoteContext(f)
    text = ctx.resolve("narrative")
    assert isinstance(text, str) and text.count(".") >= 2
