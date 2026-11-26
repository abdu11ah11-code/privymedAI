"""Seeded generators for the surface strings of each entity type.

The factory returns *values only*; character offsets are recorded later by
the template engine as it assembles text. Every value carries a ``fmt`` tag
(e.g. ``"dmy_slash"``) so evaluation can break errors down by surface format.

Determinism: all randomness flows from one ``random.Random(seed)`` plus
Faker instances seeded from the same seed, so an identical sequence of calls
yields identical output.
"""

from __future__ import annotations

import datetime as dt
import random
import re
import string
import unicodedata
from dataclasses import dataclass
from typing import Literal

from faker import Faker

from privymed.data_generation import pools
from privymed.schema import EntityType

Gender = Literal["m", "f"]
Origin = Literal["pk", "intl"]

NAME_STYLES: tuple[str, ...] = (
    "full", "last_first", "initial_last", "first_only", "last_only", "upper", "lower",
)  # fmt: skip

DATE_FORMATS: tuple[str, ...] = (
    "dmy_slash", "dmy_dash", "dmy_dot", "iso", "mdy_slash", "dmy_short", "dmy_nopad",
    "d_month_y", "month_d_y", "ordinal_month_y", "d_mon_y", "mon_d", "d_month", "month_y",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Person:
    first: str
    last: str
    gender: Gender
    origin: Origin
    middle: str | None = None

    @property
    def given(self) -> str:
        return f"{self.first} {self.middle}" if self.middle else self.first


@dataclass(frozen=True, slots=True)
class Value:
    """A generated surface string, its entity type, and its format tag."""

    text: str
    label: EntityType
    fmt: str

    def __post_init__(self) -> None:
        if not self.text or self.text != self.text.strip():
            raise ValueError(f"generated {self.label} value has bad boundaries: {self.text!r}")


def _ascii_slug(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", folded.lower())


class EntityFactory:
    """Produces synthetic entity values. ``pk_ratio`` = share of Pakistani-style values."""

    def __init__(self, seed: int, pk_ratio: float = 0.6) -> None:
        if not 0.0 <= pk_ratio <= 1.0:
            raise ValueError("pk_ratio must be in [0, 1]")
        self.rng = random.Random()
        self.pk_ratio = pk_ratio
        self._fakers: dict[str, Faker] = {loc: Faker(loc) for loc in pools.INTL_LOCALES}
        self.reseed(seed)

    def reseed(self, seed: int) -> None:
        """Reset all randomness. Cheap, so it can be called once per document."""
        self.rng.seed(seed)
        for i, fk in enumerate(self._fakers.values()):
            fk.seed_instance(seed * 1009 + i)

    # ------------------------------------------------------------------ helpers
    def _digits(self, n: int) -> str:
        return "".join(self.rng.choice(string.digits) for _ in range(n))

    def _letters(self, n: int) -> str:
        return "".join(self.rng.choice(string.ascii_uppercase) for _ in range(n))

    def _is_pk(self) -> bool:
        return self.rng.random() < self.pk_ratio

    def _faker(self) -> Faker:
        return self._fakers[self.rng.choice(pools.INTL_LOCALES)]

    # ------------------------------------------------------------------ people
    def person(self, gender: Gender | None = None, origin: Origin | None = None) -> Person:
        g: Gender = gender if gender is not None else ("m" if self.rng.random() < 0.5 else "f")
        o: Origin = origin if origin is not None else ("pk" if self._is_pk() else "intl")
        if o == "pk":
            first = self.rng.choice(pools.PK_MALE_FIRST if g == "m" else pools.PK_FEMALE_FIRST)
            last = self.rng.choice(pools.PK_SURNAMES)
            middle = None
            if g == "m" and self.rng.random() < 0.2:
                first, middle = "Muhammad", first
            return Person(first=first, last=last, gender=g, origin=o, middle=middle)
        fk = self._faker()
        first = fk.first_name_male() if g == "m" else fk.first_name_female()
        return Person(first=first, last=fk.last_name(), gender=g, origin=o)

    def name_text(self, person: Person, style: str | None = None) -> tuple[str, str]:
        """Render a person's name. Titles (Dr., Mr.) are never included — see annotation guide."""
        s = style or self.rng.choices(NAME_STYLES, weights=(50, 8, 10, 8, 14, 6, 4))[0]
        full = f"{person.given} {person.last}"
        match s:
            case "full":
                text = full
            case "last_first":
                text = f"{person.last}, {person.given}"
            case "initial_last":
                text = f"{person.first[0]}. {person.last}"
            case "first_only":
                text = person.first
            case "last_only":
                text = person.last
            case "upper":
                text = full.upper()
            case "lower":
                text = full.lower()
            case _:
                raise ValueError(f"unknown name style {s!r}")
        return text, s

    def patient_name(self, person: Person, style: str | None = None) -> Value:
        text, fmt = self.name_text(person, style)
        return Value(text, EntityType.PATIENT, fmt)

    def staff_name(self, person: Person, style: str | None = None) -> Value:
        text, fmt = self.name_text(person, style)
        return Value(text, EntityType.STAFF, fmt)

    # ------------------------------------------------------------------ dates
    def random_date(self, kind: Literal["dob", "visit"] = "visit") -> dt.date:
        lo, hi = (dt.date(1935, 1, 1), dt.date(2024, 12, 31))
        if kind == "visit":
            lo, hi = dt.date(2019, 1, 1), dt.date(2026, 12, 31)
        return lo + dt.timedelta(days=self.rng.randint(0, (hi - lo).days))

    def format_date(self, d: dt.date, fmt: str | None = None) -> Value:
        f = fmt or self.rng.choice(DATE_FORMATS)
        month, mon = pools.MONTHS[d.month - 1], pools.MONTHS[d.month - 1][:3]
        day_ord = f"{d.day}{_ordinal_suffix(d.day)}"
        text = {
            "dmy_slash": f"{d.day:02d}/{d.month:02d}/{d.year}",
            "dmy_dash": f"{d.day:02d}-{d.month:02d}-{d.year}",
            "dmy_dot": f"{d.day:02d}.{d.month:02d}.{d.year}",
            "iso": d.isoformat(),
            "mdy_slash": f"{d.month:02d}/{d.day:02d}/{d.year}",
            "dmy_short": f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d}",
            "dmy_nopad": f"{d.day}/{d.month}/{d.year}",
            "d_month_y": f"{d.day} {month} {d.year}",
            "month_d_y": f"{month} {d.day}, {d.year}",
            "ordinal_month_y": f"{day_ord} {month} {d.year}",
            "d_mon_y": f"{d.day:02d}-{mon}-{d.year}",
            "mon_d": f"{mon} {d.day}",
            "d_month": f"{d.day} {month}",
            "month_y": f"{month} {d.year}",
        }.get(f)
        if text is None:
            raise ValueError(f"unknown date format {f!r}")
        return Value(text, EntityType.DATE, f)

    def date(self, kind: Literal["dob", "visit"] = "visit", fmt: str | None = None) -> Value:
        return self.format_date(self.random_date(kind), fmt)

    # ------------------------------------------------------------------ phones
    def phone(self) -> Value:
        r = self.rng.random()
        if r < 0.6:  # Pakistani mobile
            p, n = self.rng.choice(pools.PK_MOBILE_PREFIXES), self._digits(7)
            fmt, text = self.rng.choice(
                (
                    ("pk_mobile_dash", f"0{p}-{n}"),
                    ("pk_mobile_space", f"0{p} {n}"),
                    ("pk_mobile_plain", f"0{p}{n}"),
                    ("pk_mobile_intl", f"+92 {p} {n}"),
                    ("pk_mobile_intl_dash", f"+92-{p}-{n}"),
                    ("pk_mobile_intl_plain", f"+92{p}{n}"),
                    ("pk_mobile_0092", f"0092 {p} {n}"),
                    ("pk_mobile_split", f"0{p}-{n[:3]}-{n[3:]}"),
                )
            )
        elif r < 0.8:  # Pakistani landline
            _, area, _ = self.rng.choice(pools.PK_CITIES)
            # Subscriber numbers never start with 0 or 1.
            n = str(self.rng.randint(2, 9)) + self._digits(7 if area in ("042", "021") else 6)
            fmt, text = self.rng.choice(
                (
                    ("pk_landline_paren", f"({area}) {n}"),
                    ("pk_landline_dash", f"{area}-{n}"),
                    ("pk_landline_intl", f"+92 {area[1:]} {n}"),
                )
            )
        elif r < 0.9:  # UK, Ofcom drama range 020 7946 0000-0999
            n = self._digits(3)
            fmt, text = self.rng.choice(
                (("uk_intl", f"+44 20 7946 0{n}"), ("uk_national", f"020 7946 0{n}"))
            )
        else:  # US, fictional 555-0100..0199
            area, n = str(self.rng.randint(201, 989)), self._digits(2)
            fmt, text = self.rng.choice(
                (
                    ("us_paren", f"({area}) 555-01{n}"),
                    ("us_dash", f"{area}-555-01{n}"),
                    ("us_intl", f"+1 {area} 555 01{n}"),
                    ("us_dot", f"{area}.555.01{n}"),
                )
            )
        return Value(text, EntityType.PHONE, fmt)

    # ------------------------------------------------------------------ CNIC
    def cnic(self, gender: Gender | None = None) -> Value:
        """Pakistani CNIC: 5-7-1 digits; final digit odd for male, even for female."""
        head = str(self.rng.randint(1, 7)) + self._digits(4)
        mid = self._digits(7)
        g = gender or self.rng.choice(("m", "f"))
        last = str(self.rng.choice((1, 3, 5, 7, 9) if g == "m" else (0, 2, 4, 6, 8)))
        fmt = self.rng.choices(("dashed", "plain", "spaced"), weights=(85, 10, 5))[0]
        sep = {"dashed": "-", "plain": "", "spaced": " "}[fmt]
        return Value(f"{head}{sep}{mid}{sep}{last}", EntityType.CNIC, fmt)

    # ------------------------------------------------------------------ IDs
    def record_id(self) -> Value:
        year = str(self.rng.randint(2015, 2026))
        fmt, text = self.rng.choice(
            (
                ("mrn_year", f"MRN-{year}-{self._digits(6)}"),
                ("mr_digits", f"MR{self._digits(8)}"),
                ("pt_dash", f"PT-{self._digits(6)}"),
                ("hosp_slash", f"{self._letters(3)}/{year[2:]}/{self._digits(5)}"),
                ("letters_digits", f"{self._letters(2)}{self._digits(7)}"),
                ("hash_digits", f"#{self._digits(7)}"),
                ("ip_year", f"IP-{year}/{self._digits(4)}"),
                ("digit_groups", f"{self._digits(4)}-{self._digits(4)}-{self._digits(2)}"),
                ("lab", f"LAB{year[2:]}-{self._digits(5)}"),
                ("adm", f"ADM{self._digits(6)}"),
                ("plain_digits", self._digits(self.rng.randint(6, 9))),
            )
        )
        return Value(text, EntityType.ID, fmt)

    # ------------------------------------------------------------------ hospitals
    def hospital(self) -> Value:
        for _ in range(50):
            core = self.rng.choice(pools.HOSPITAL_CORES)
            name = f"{core} {self.rng.choice(pools.HOSPITAL_SUFFIXES)}"
            if not any(bad in name.lower() for bad in pools.HOSPITAL_BLOCKLIST):
                break
        else:  # pragma: no cover - pools are designed so this cannot happen
            raise RuntimeError("could not generate a non-blocklisted hospital name")
        if self.rng.random() < 0.1:
            acronym = "".join(w[0] for w in re.split(r"[\s-]+", name) if w[0].isupper())
            if len(acronym) >= 2:
                return Value(acronym, EntityType.HOSPITAL, "acronym")
        return Value(name, EntityType.HOSPITAL, "full")

    # ------------------------------------------------------------------ email
    def email(self, person: Person | None = None) -> Value:
        domain = self.rng.choice(pools.EMAIL_DOMAINS)
        fmt = "freemail"
        if self.rng.random() < 0.2:
            core = _ascii_slug(self.rng.choice(pools.HOSPITAL_CORES))
            kind = self.rng.choice(("hospital", "health", "clinic"))
            tld = self.rng.choice(("com.pk", "org.pk", "org", "com"))
            domain, fmt = f"{core}{kind}.{tld}", "org"
        if person is None:
            prefix = self.rng.choice(("info", "contact", "records", "patient", "user"))
            local = prefix + self._digits(self.rng.randint(0, 4))
            return Value(f"{local}@{domain}", EntityType.EMAIL, f"{fmt}_generic")
        f, last = _ascii_slug(person.first), _ascii_slug(person.last)
        local = self.rng.choice(
            (
                f"{f}.{last}",
                f"{f}{last}",
                f"{f[0]}.{last}",
                f"{f}_{last}",
                f"{f}.{last}{self._digits(2)}",
                f"{last}.{f}",
                f"{f}{self._digits(self.rng.randint(2, 4))}",
            )
        )
        return Value(f"{local}@{domain}", EntityType.EMAIL, f"{fmt}_name")

    # ------------------------------------------------------------------ address
    def address(self) -> Value:
        if not self._is_pk():
            fk = self._fakers[self.rng.choice(("en_GB", "en_US", "en_AU", "en_CA"))]
            text = re.sub(r"\s*\n\s*", ", ", fk.address().strip())
            return Value(text, EntityType.ADDRESS, "intl")
        city, _, localities = self.rng.choice(pools.PK_CITIES)
        loc = self.rng.choice(localities)
        n, street = self.rng.randint(1, 999), self.rng.randint(1, 60)
        letter = self.rng.choice("ABCDEFGHJKLMN")
        building = self.rng.choice(pools.PK_BUILDING_WORDS)
        flat = f"{self.rng.randint(1, 20)}{self.rng.choice('ABCD')}"
        templates = {
            "pk_house_street": f"House No. {n}, Street {street}, {loc}, {city}",
            "pk_house_short": f"H# {n}, St# {street}, {loc}, {city}",
            "pk_plot_letter": f"{n}-{letter}, {loc}, {city}",
            "pk_flat": f"Flat {flat}, {building} Heights, {loc}, {city}",
            "pk_plot_block": f"Plot {n}, Block {letter}, {loc}, {city}",
            "pk_locality": f"{loc}, {city}",
            "pk_mohallah": f"Mohallah {building}, {city}",
        }
        fmt = self.rng.choice(tuple(templates))
        text = templates[fmt]
        if fmt != "pk_locality" and self.rng.random() < 0.15:
            text += f" {self._digits(5)}"
        if self.rng.random() < 0.1:
            text += ", Pakistan"
        return Value(text, EntityType.ADDRESS, fmt)


def _ordinal_suffix(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
