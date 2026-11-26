"""Template engine: renders template families into gold-annotated documents.

Key property: **labels are correct by construction.** Entity values are
appended through :class:`TextBuilder`, which records each span's offsets at
the moment the value is written. Nothing is located after the fact by string
search (which would mislabel repeated or overlapping strings).

Template syntax
---------------
``{slot}`` / ``{slot:modifier}``
    Insert an entity or a non-entity filler from the note's :class:`NoteContext`.
    For names the modifier is a name style (``last_only``, ``initial_last`` …);
    for dates it is a date format (``iso``, ``d_month_y`` …).
``[[a|b|c]]``
    Choose one alternative uniformly. Alternatives may contain slots and may be
    empty (``[[|, ]]``). Not nestable.

A :class:`TemplateFamily` is an ordered list of :class:`Section` objects; each
section has alternative wordings and an inclusion probability. Families are
the unit of the train/dev/test split (no family appears in two splits).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from privymed.data_generation import pools
from privymed.data_generation.entities import (
    DATE_FORMATS,
    NAME_STYLES,
    EntityFactory,
    Gender,
    Person,
    Value,
)
from privymed.data_generation.noise import CLEAN, NoiseApplier, NoiseProfile, choose_profile
from privymed.schema import Document, EntityType, Span

_CHOICE = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)
_SLOT = re.compile(r"\{([a-z0-9_.]+)(?::([a-z0-9_]+))?\}")

SHARED_SURNAME_RATE = 0.08
NARRATIVE_RATE = 0.6
BUNDLE_SEPARATORS = ("\n\n", "\n\n---\n\n", "\n\n==========\n\n", "\n\n[Page break]\n\n")

PERSON_ROLES = ("patient", "patient2", "patient3", "relative", "staff1", "staff2", "staff3")
# Name styles used for repeat mentions when the template gives no modifier.
_REPEAT_STYLES = ("full", "last_only", "initial_last", "first_only")


# ============================================================================ builder
class TextBuilder:
    """Accumulates text and records entity spans at append time."""

    def __init__(self, noise: NoiseApplier | None = None) -> None:
        self._parts: list[str] = []
        self._length = 0
        self._spans: list[Span] = []
        self._noise = noise

    def _append(self, text: str) -> None:
        if text:
            self._parts.append(text)
            self._length += len(text)

    def add_text(self, text: str) -> None:
        self._append(self._noise.literal(text) if self._noise and text else text)

    def add_entity(self, value: Value) -> None:
        if self._noise:
            value = self._noise.entity(value)
        start = self._length
        self._append(value.text)
        self._spans.append(Span(start=start, end=self._length, label=value.label, fmt=value.fmt))

    @property
    def text(self) -> str:
        return "".join(self._parts)

    def build(self, doc_id: str, metadata: dict[str, str | int | float | bool]) -> Document:
        return Document(doc_id=doc_id, text=self.text, spans=tuple(self._spans), metadata=metadata)


# ============================================================================ context
class NoteContext:
    """The cast and facts of one note. Every slot resolves consistently within the note."""

    def __init__(self, factory: EntityFactory) -> None:
        self.f = factory
        self.rng = factory.rng
        self._people: dict[str, Person] = {}
        self._mentions: dict[str, int] = {}
        self._dates: dict[str, dt.date] = {}
        self._cache: dict[str, Value | str] = {}
        # Notes usually use one date style; ~20% mix styles.
        self._date_fmt = self.rng.choice(DATE_FORMATS[:10])
        self._mix_dates = self.rng.random() < 0.2

    # ---------------------------------------------------------------- people
    def person(self, role: str) -> Person:
        if role not in self._people:
            if role == "relative":
                _, g = self._relation()
                gender: Gender = "m" if g == "m" else "f"
                # Relatives usually share the patient's origin.
                self._people[role] = self.f.person(
                    gender=gender, origin=self.person("patient").origin
                )
            elif role == "staff1" and self.rng.random() < SHARED_SURNAME_RATE:
                # Hard case: doctor shares the patient's surname
                # ("Ali Khan" seen by "Dr. Imran Khan").
                patient = self.person("patient")
                donor = self.f.person(origin=patient.origin)
                self._people[role] = Person(
                    first=donor.first, last=patient.last, gender=donor.gender, origin=patient.origin
                )
            else:
                self._people[role] = self.f.person()
        return self._people[role]

    def _relation(self) -> tuple[str, str]:
        key = "_relation"
        if key not in self._cache:
            age = self.age()
            if age < 18:  # minors: parents or guardians only
                allowed = {"mother", "father", "guardian", "uncle"}
            elif age < 35:  # adult children unlikely
                allowed = {r for r, _ in pools.RELATIONS} - {"son", "daughter"}
            else:
                allowed = {r for r, _ in pools.RELATIONS}
            options = [rg for rg in pools.RELATIONS if rg[0] in allowed]
            rel, g = self.rng.choice(options)
            self._cache[key] = f"{rel}|{g}"
        rel, g = str(self._cache[key]).split("|")
        return rel, g

    def _name(self, role: str, style: str | None) -> Value:
        person = self.person(role)
        count = self._mentions.get(role, 0)
        self._mentions[role] = count + 1
        if style is None:
            style = "full" if count == 0 else self.rng.choice(_REPEAT_STYLES)
        if style not in NAME_STYLES:
            raise ValueError(f"unknown name style {style!r}")
        label = EntityType.STAFF if role.startswith("staff") else EntityType.PATIENT
        text, fmt = self.f.name_text(person, style)
        return Value(text, label, fmt)

    def _title(self, role: str) -> str:
        if role.startswith("staff"):
            return "Dr."
        p = self.person(role)
        return "Mr." if p.gender == "m" else self.rng.choice(("Ms.", "Mrs."))

    # ---------------------------------------------------------------- dates
    def date_obj(self, name: str) -> dt.date:
        if name not in self._dates:
            rng = self.rng
            if name == "dob":
                anchor = self.date_obj("visit")
                d = anchor - dt.timedelta(days=rng.randint(365, 95 * 365))
            elif name == "discharge":
                d = self.date_obj("admit") + dt.timedelta(days=rng.randint(1, 14))
            elif name == "followup":
                d = self.date_obj("visit") + dt.timedelta(days=rng.randint(7, 60))
            elif name == "report":
                d = self.date_obj("visit") + dt.timedelta(days=rng.randint(0, 3))
            elif name == "prev":
                d = self.date_obj("visit") - dt.timedelta(days=rng.randint(30, 180))
            elif name == "admit":
                d = self.date_obj("visit") - dt.timedelta(days=rng.randint(0, 5))
            else:
                d = self.f.random_date("visit")
            self._dates[name] = d
        return self._dates[name]

    def _date(self, name: str, fmt: str | None) -> Value:
        if fmt is None:
            fmt = self.rng.choice(DATE_FORMATS) if self._mix_dates else self._date_fmt
        return self.f.format_date(self.date_obj(name), fmt)

    def age(self) -> int:
        dob, visit = self.date_obj("dob"), self.date_obj("visit")
        return visit.year - dob.year - ((visit.month, visit.day) < (dob.month, dob.day))

    # ---------------------------------------------------------------- resolution
    def resolve(self, slot: str, modifier: str | None = None) -> Value | str:
        head, _, attr = slot.partition(".")

        if head in PERSON_ROLES:
            if attr == "name":
                return self._name(head, modifier)
            if attr == "dob" and head == "patient":
                return self._date("dob", modifier)
            if attr == "title":
                return self._title(head)
            if attr in ("subj", "obj", "poss", "subj_cap", "poss_cap"):
                word = _pronoun(self.person(head).gender, attr.removesuffix("_cap"))
                return word.capitalize() if attr.endswith("_cap") else word
            return self._cached(slot, lambda: self._person_attr(head, attr))
        if head == "date":
            return self._date(attr or "visit", modifier)
        if head == "id":
            return self._cached(slot, self.f.record_id)
        if head.startswith("hospital"):
            return self._cached(slot, lambda: self._hospital_attr(attr))
        if modifier is not None:
            raise ValueError(f"filler slot {slot!r} does not take a modifier")
        # Numbered fillers ({medication2}, {time3}) are independent draws of the same kind.
        base = head.rstrip("0123456789")
        return self._cached(slot, lambda: self._filler(base, attr))

    def _cached(self, key: str, make: Callable[[], Value | str]) -> Value | str:
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    def _person_attr(self, role: str, attr: str) -> Value | str:
        p = self.person(role)
        match attr:
            case "cnic":
                return self.f.cnic(gender=p.gender)
            case "phone":
                return self.f.phone()
            case "email":
                return self.f.email(p)
            case "address":
                return self.f.address()
            case "mrn":
                return self.f.record_id()
            case "credential":
                return self.rng.choice(pools.CREDENTIALS)
            case "relation" if role == "relative":
                return self._relation()[0]
        raise ValueError(f"unknown person attribute {role}.{attr}")

    def _hospital_attr(self, attr: str) -> Value:
        match attr:
            case "":
                return self.f.hospital()
            case "phone":
                return self.f.phone()
            case "address":
                return self.f.address()
            case "email":
                return self.f.email(None)
        raise ValueError(f"unknown hospital attribute {attr!r}")

    def _filler(self, head: str, attr: str) -> str:
        rng = self.rng
        match head:
            case "age":
                return str(self.age())
            case "sex":
                return "male" if self.person("patient").gender == "m" else "female"
            case "sex_short":
                return "M" if self.person("patient").gender == "m" else "F"
            case "hb":
                return f"{rng.uniform(7.5, 16.5):.1f}"
            case "wbc":
                return f"{rng.uniform(3.0, 18.0):.1f}"
            case "plt":
                return str(rng.randint(90, 450))
            case "glucose":
                return str(rng.randint(70, 280))
            case "creatinine":
                return f"{rng.uniform(0.5, 3.5):.2f}"
            case "sats":  # oxygen saturation (no digits: numbered-filler suffixes are stripped)
                return str(rng.randint(88, 100))
            case "diagnosis":
                return rng.choice(pools.DIAGNOSES)
            case "complaint":
                return rng.choice(pools.COMPLAINTS)
            case "medication":
                return rng.choice(pools.MEDICATIONS)
            case "freq":
                return rng.choice(pools.FREQUENCIES)
            case "duration":
                return rng.choice(pools.DURATIONS)
            case "specialty":
                return rng.choice(pools.SPECIALTIES)
            case "ward":
                return rng.choice(pools.WARDS)
            case "rel_date":
                return rng.choice(pools.RELATIVE_DATES)
            case "city":  # a lone city mention: deliberately NOT annotated
                return rng.choice(pools.PK_CITIES)[0]
            case "time":
                hour, minute = rng.randint(1, 12), rng.choice((0, 15, 30, 45))
                return f"{hour}:{minute:02d} {rng.choice(('AM', 'PM'))}"
            case "bp":
                return f"{rng.randint(100, 170)}/{rng.randint(60, 100)}"
            case "pulse":
                return str(rng.randint(58, 120))
            case "temp":
                return f"{rng.uniform(97.0, 103.0):.1f}"
            case "narrative":  # 2-4 entity-free clinical sentences
                return " ".join(rng.sample(self.f.narrative, rng.randint(2, 4)))
        raise ValueError(f"unknown slot {head!r}")


def _pronoun(gender: str, kind: str) -> str:
    table = {"subj": ("he", "she"), "obj": ("him", "her"), "poss": ("his", "her")}
    return table[kind][0 if gender == "m" else 1]


# ============================================================================ templates
@dataclass(frozen=True)
class Section:
    variants: tuple[str, ...]
    p: float = 1.0

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError("section needs at least one variant")
        if not 0.0 < self.p <= 1.0:
            raise ValueError("section probability must be in (0, 1]")


@dataclass(frozen=True)
class TemplateFamily:
    family_id: str
    doc_type: str
    sections: tuple[Section, ...]
    sep: str = "\n"
    tags: tuple[str, ...] = field(default_factory=tuple)
    # Indices of sections after which an entity-free narrative paragraph may be inserted.
    narrative_after: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        bad = [i for i in self.narrative_after if not 0 <= i < len(self.sections)]
        if bad:
            raise ValueError(f"{self.family_id}: narrative_after indices out of range: {bad}")

    @property
    def entity_free(self) -> bool:
        return "entity_free" in self.tags


def render_line(line: str, ctx: NoteContext, builder: TextBuilder) -> None:
    line = _CHOICE.sub(lambda m: ctx.rng.choice(m.group(1).split("|")), line)
    pos = 0
    for m in _SLOT.finditer(line):
        builder.add_text(line[pos : m.start()])
        value = ctx.resolve(m.group(1), m.group(2))
        if isinstance(value, Value):
            builder.add_entity(value)
        else:
            builder.add_text(value)
        pos = m.end()
    builder.add_text(line[pos:])


def derive_seed(global_seed: int, family_id: str, index: int) -> int:
    """Stable per-document seed (independent of Python's randomised ``hash``)."""
    digest = hashlib.sha256(f"{global_seed}:{family_id}:{index}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _render_family(family: TemplateFamily, ctx: NoteContext, builder: TextBuilder) -> None:
    first = True
    for i, section in enumerate(family.sections):
        if section.p < 1.0 and ctx.rng.random() >= section.p:
            continue
        if not first:
            builder.add_text(family.sep)
        render_line(ctx.rng.choice(section.variants), ctx, builder)
        first = False
        if i in family.narrative_after and ctx.rng.random() < NARRATIVE_RATE:
            builder.add_text(family.sep)
            render_line("{narrative" + str(i) + "}", ctx, builder)


def _start(
    key: str, factory: EntityFactory, global_seed: int, index: int, noise: NoiseProfile | None
) -> tuple[NoteContext, TextBuilder, NoiseProfile]:
    factory.reseed(derive_seed(global_seed, key, index))
    ctx = NoteContext(factory)
    # Noise uses its own RNG stream so content is identical with and without noise:
    # every noisy document has an exact clean twin (enables paired robustness evaluation).
    noise_rng = random.Random(derive_seed(global_seed, key + "#noise", index))
    profile = noise if noise is not None else choose_profile(noise_rng)
    applier = NoiseApplier(profile, noise_rng) if profile != CLEAN else None
    return ctx, TextBuilder(applier), profile


def generate_document(
    family: TemplateFamily,
    factory: EntityFactory,
    global_seed: int,
    index: int,
    noise: NoiseProfile | None = None,
) -> Document:
    """Render one document. ``noise=None`` samples a noise profile; pass ``CLEAN`` to disable."""
    ctx, builder, profile = _start(family.family_id, factory, global_seed, index, noise)
    _render_family(family, ctx, builder)
    return builder.build(
        doc_id=f"{family.family_id}-{index:05d}",
        metadata={
            "family": family.family_id,
            "doc_type": family.doc_type,
            "index": index,
            "global_seed": global_seed,
            "noise": profile.name,
        },
    )


def generate_bundle(
    families: Sequence[TemplateFamily],
    factory: EntityFactory,
    global_seed: int,
    index: int,
    noise: NoiseProfile | None = None,
) -> Document:
    """Render several documents about the *same* patient into one record (EHR-export style).

    All parts share one :class:`NoteContext`, so the patient, relatives,
    hospital and key dates are consistent across parts. For split hygiene,
    callers must only bundle families from the same split.
    """
    if len(families) < 2:
        raise ValueError("a bundle needs at least two families")
    key = "+".join(f.family_id for f in families)
    ctx, builder, profile = _start(key, factory, global_seed, index, noise)
    for n, family in enumerate(families):
        if n:
            builder.add_text(ctx.rng.choice(BUNDLE_SEPARATORS))
        _render_family(family, ctx, builder)
    return builder.build(
        doc_id=f"bundle-{key}-{index:05d}",
        metadata={
            "family": key,
            "doc_type": "bundle",
            "index": index,
            "global_seed": global_seed,
            "noise": profile.name,
        },
    )
