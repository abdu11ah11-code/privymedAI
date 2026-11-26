from __future__ import annotations

import datetime as dt
import re

import pytest

from privymed.data_generation.engine import (
    NoteContext,
    Section,
    TemplateFamily,
    TextBuilder,
    derive_seed,
    generate_document,
    render_line,
)
from privymed.data_generation.entities import EntityFactory, Value
from privymed.data_generation.noise import CLEAN, NoiseProfile
from privymed.schema import Document, EntityType


def gen(
    fam: TemplateFamily, f: EntityFactory, seed: int, i: int, noise: NoiseProfile = CLEAN
) -> Document:
    return generate_document(fam, f, seed, i, noise=noise)


@pytest.fixture(scope="module")
def factory() -> EntityFactory:
    return EntityFactory(0)


def _one_line_family(line: str, fid: str = "t") -> TemplateFamily:
    return TemplateFamily(family_id=fid, doc_type="test", sections=(Section((line,)),))


DEMO = TemplateFamily(
    family_id="demo",
    doc_type="discharge",
    sections=(
        Section(("{hospital}\nDISCHARGE SUMMARY",)),
        Section(
            (
                "Patient: {patient.name}[[| (MRN {patient.mrn})]]\nDOB: {patient.dob}",
                "Name: {patient.name:last_first}  MRN: {patient.mrn}  DOB: {patient.dob}",
            )
        ),
        Section(("Admitted on {date.admit} with {complaint}; discharged {date.discharge}.",)),
        Section(("Contact: {patient.phone} / {patient.email}",), p=0.5),
        Section(("Consultant: Dr. {staff1.name}, {staff1.credential}",)),
    ),
)


# ------------------------------------------------------------------ builder
def test_builder_records_exact_offsets() -> None:
    b = TextBuilder()
    b.add_text("Pt ")
    b.add_entity(Value("Ali Khan", EntityType.PATIENT, "full"))
    b.add_text(", ph ")
    b.add_entity(Value("0300-1234567", EntityType.PHONE, "pk_mobile_dash"))
    doc = b.build("x", {})
    assert [doc.span_text(s) for s in doc.spans] == ["Ali Khan", "0300-1234567"]
    assert doc.spans[1].fmt == "pk_mobile_dash"


def test_adjacent_entities_keep_separate_spans() -> None:
    b = TextBuilder()
    b.add_entity(Value("MR123", EntityType.ID, "x"))
    b.add_entity(Value("Ali", EntityType.PATIENT, "x"))
    doc = b.build("x", {})
    assert [s.range for s in doc.spans] == [(0, 5), (5, 8)]


# ------------------------------------------------------------------ labels by construction
def test_every_span_surface_matches_its_label(factory: EntityFactory) -> None:
    for i in range(300):
        doc = gen(DEMO, factory, 1, i)
        for s in doc.spans:
            surface = doc.span_text(s)
            if s.label is EntityType.EMAIL:
                assert "@" in surface
            if s.label is EntityType.PHONE:
                assert sum(c.isdigit() for c in surface) >= 9
            if s.label is EntityType.DATE:
                assert re.search(r"\d", surface)


def test_same_person_is_consistent_across_mentions(factory: EntityFactory) -> None:
    fam = _one_line_family("{patient.name:full} ... {patient.name:last_only}")
    for i in range(100):
        doc = gen(fam, factory, 2, i)
        full, last = (doc.span_text(s) for s in doc.spans)
        assert full.endswith(" " + last)


def test_first_mention_defaults_to_full_name(factory: EntityFactory) -> None:
    fam = _one_line_family("{staff1.name}")
    for i in range(50):
        doc = gen(fam, factory, 3, i)
        assert " " in doc.span_text(doc.spans[0])


def test_staff_and_patient_labels(factory: EntityFactory) -> None:
    doc = gen(_one_line_family("{patient.name} {relative.name} {staff2.name}"), factory, 4, 0)
    assert [s.label for s in doc.spans] == [
        EntityType.PATIENT,
        EntityType.PATIENT,
        EntityType.STAFF,
    ]


def test_age_consistent_with_dob_and_visit(factory: EntityFactory) -> None:
    fam = _one_line_family("{age}|{patient.dob:iso}|{date.visit:iso}")
    for i in range(200):
        doc = gen(fam, factory, 5, i)
        age, dob, visit = doc.text.split("|")
        d, v = dt.date.fromisoformat(dob), dt.date.fromisoformat(visit)
        assert int(age) == v.year - d.year - ((v.month, v.day) < (d.month, d.day))
        assert 1 <= int(age) <= 95


def test_discharge_after_admit_and_followup_after_visit(factory: EntityFactory) -> None:
    fam = _one_line_family(
        "{date.admit:iso} {date.discharge:iso} {date.visit:iso} {date.followup:iso}"
    )
    for i in range(200):
        a, d, v, f = map(dt.date.fromisoformat, gen(fam, factory, 6, i).text.split())
        assert a < d and v < f and a <= v


def test_relative_gender_matches_relation(factory: EntityFactory) -> None:
    ctx_factory = EntityFactory(7)
    female = {"mother", "wife", "daughter", "sister"}
    for i in range(200):
        ctx_factory.reseed(i)
        ctx = NoteContext(ctx_factory)
        relation = ctx.resolve("relative.relation")
        assert isinstance(relation, str)
        expected = "f" if relation in female else "m"
        assert ctx.person("relative").gender == expected


def test_relation_is_plausible_for_patient_age() -> None:
    f = EntityFactory(13)
    for i in range(500):
        f.reseed(i)
        ctx = NoteContext(f)
        relation = ctx.resolve("relative.relation")
        if ctx.age() < 18:
            assert relation in {"mother", "father", "guardian", "uncle"}
        elif ctx.age() < 35:
            assert relation not in {"son", "daughter"}


def test_fillers_are_never_annotated(factory: EntityFactory) -> None:
    fam = _one_line_family("{city} {time} {rel_date} {diagnosis} {medication} {age} {bp}")
    for i in range(50):
        assert gen(fam, factory, 8, i).spans == ()


# ------------------------------------------------------------------ syntax
def test_choice_syntax_includes_empty_alternative(factory: EntityFactory) -> None:
    fam = _one_line_family("A[[|B|C]]D")
    seen = {gen(fam, factory, 9, i).text for i in range(100)}
    assert seen == {"AD", "ABD", "ACD"}


def test_choice_alternatives_may_contain_slots(factory: EntityFactory) -> None:
    fam = _one_line_family("[[Tel {patient.phone}|Email {patient.email}]]")
    labels = {gen(fam, factory, 10, i).spans[0].label for i in range(60)}
    assert labels == {EntityType.PHONE, EntityType.EMAIL}


def test_optional_section_probability(factory: EntityFactory) -> None:
    fam = TemplateFamily("p", "t", (Section(("X",)), Section(("Y",), p=0.5)), sep="")
    share = sum(gen(fam, factory, 11, i).text == "XY" for i in range(1000)) / 1000
    assert 0.44 < share < 0.56


def test_unknown_slot_raises(factory: EntityFactory) -> None:
    with pytest.raises(ValueError, match="unknown slot"):
        gen(_one_line_family("{nonsense}"), factory, 0, 0)


def test_unknown_name_style_raises(factory: EntityFactory) -> None:
    with pytest.raises(ValueError, match="name style"):
        gen(_one_line_family("{patient.name:shouting}"), factory, 0, 0)


def test_modifier_on_filler_raises(factory: EntityFactory) -> None:
    with pytest.raises(ValueError, match="modifier"):
        gen(_one_line_family("{city:upper}"), factory, 0, 0)


def test_section_validation() -> None:
    with pytest.raises(ValueError):
        Section(())
    with pytest.raises(ValueError):
        Section(("x",), p=0.0)


# ------------------------------------------------------------------ determinism
def test_documents_are_order_independent() -> None:
    a = EntityFactory(0)
    for i in range(5):
        gen(DEMO, a, 42, i)
    after_others = gen(DEMO, a, 42, 5)
    fresh = gen(DEMO, EntityFactory(999), 42, 5)
    assert after_others == fresh


def test_derive_seed_is_stable_and_distinct() -> None:
    assert derive_seed(42, "demo", 1) == derive_seed(42, "demo", 1)
    assert len({derive_seed(42, "demo", i) for i in range(1000)}) == 1000
    assert derive_seed(42, "demo", 1) != derive_seed(42, "other", 1)


def test_render_line_directly(factory: EntityFactory) -> None:
    factory.reseed(1)
    b = TextBuilder()
    render_line("ID {id.lab}; again {id.lab}", NoteContext(factory), b)
    doc = b.build("x", {})
    assert doc.span_text(doc.spans[0]) == doc.span_text(doc.spans[1])
