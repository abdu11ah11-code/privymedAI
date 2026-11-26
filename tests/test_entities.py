from __future__ import annotations

import datetime as dt
import re
from collections import Counter

import pytest

from privymed.data_generation import pools
from privymed.data_generation.entities import (
    DATE_FORMATS,
    NAME_STYLES,
    EntityFactory,
    Value,
)
from privymed.schema import EntityType

N = 2000


def _sample_all(seed: int) -> list[str]:
    f = EntityFactory(seed)
    out: list[str] = []
    for _ in range(100):
        p = f.person()
        out += [
            f.patient_name(p).text,
            f.date("dob").text,
            f.phone().text,
            f.cnic().text,
            f.record_id().text,
            f.hospital().text,
            f.email(p).text,
            f.address().text,
        ]
    return out


def test_same_seed_is_deterministic() -> None:
    assert _sample_all(7) == _sample_all(7)


def test_different_seeds_differ() -> None:
    assert _sample_all(7) != _sample_all(8)


def test_value_rejects_bad_boundaries() -> None:
    with pytest.raises(ValueError):
        Value(" Ali", EntityType.PATIENT, "full")


def test_pk_ratio_is_respected() -> None:
    f = EntityFactory(1, pk_ratio=0.6)
    share = sum(f.person().origin == "pk" for _ in range(N)) / N
    assert 0.55 < share < 0.65


def test_pk_ratio_validated() -> None:
    with pytest.raises(ValueError):
        EntityFactory(1, pk_ratio=1.5)


@pytest.mark.parametrize("style", NAME_STYLES)
def test_every_name_style_renders(style: str) -> None:
    f = EntityFactory(2)
    p = f.person(gender="f", origin="pk")
    text, fmt = f.name_text(p, style)
    assert fmt == style and text == text.strip() and text
    if style == "upper":
        assert text.isupper()
    if style == "last_first":
        assert text.startswith(p.last + ", ")


def test_names_never_contain_titles() -> None:
    f = EntityFactory(3)
    for _ in range(N):
        text = f.patient_name(f.person()).text
        assert not re.match(r"(?i)^(dr|mr|mrs|ms|prof)\.?\s", text), text


@pytest.mark.parametrize("fmt", DATE_FORMATS)
def test_every_date_format_renders(fmt: str) -> None:
    f = EntityFactory(4)
    v = f.format_date(dt.date(2024, 3, 2), fmt)
    assert v.fmt == fmt and v.label is EntityType.DATE


def test_date_format_examples() -> None:
    f = EntityFactory(4)
    d = dt.date(2024, 3, 2)
    assert f.format_date(d, "dmy_slash").text == "02/03/2024"
    assert f.format_date(d, "mdy_slash").text == "03/02/2024"
    assert f.format_date(d, "ordinal_month_y").text == "2nd March 2024"
    assert f.format_date(dt.date(2024, 3, 11), "ordinal_month_y").text == "11th March 2024"
    assert f.format_date(d, "d_mon_y").text == "02-Mar-2024"


def test_date_ranges() -> None:
    f = EntityFactory(5)
    for _ in range(N):
        assert dt.date(1935, 1, 1) <= f.random_date("dob") <= dt.date(2024, 12, 31)
        assert dt.date(2019, 1, 1) <= f.random_date("visit") <= dt.date(2026, 12, 31)


def test_cnic_structure_and_gender_parity() -> None:
    f = EntityFactory(6)
    for _ in range(N):
        v = f.cnic(gender="f")
        digits = re.sub(r"\D", "", v.text)
        assert len(digits) == 13 and digits[0] in "1234567"
        assert int(digits[-1]) % 2 == 0
        if v.fmt == "dashed":
            assert re.fullmatch(r"\d{5}-\d{7}-\d", v.text)


def test_international_phones_use_fictional_ranges() -> None:
    f = EntityFactory(7)
    for _ in range(N):
        v = f.phone()
        if v.fmt.startswith("uk"):
            assert "7946 0" in v.text
        if v.fmt.startswith("us"):
            assert re.search(r"555[-. ]01\d\d$", v.text), v.text


def test_pk_mobile_digit_count() -> None:
    f = EntityFactory(8)
    for _ in range(N):
        v = f.phone()
        if v.fmt.startswith("pk_mobile"):
            digits = re.sub(r"\D", "", v.text)
            assert digits.endswith(digits[-10:]) and len(digits[-10:]) == 10
            assert digits[-10] == "3"


def test_hospitals_avoid_blocklist() -> None:
    f = EntityFactory(9)
    for _ in range(N):
        name = f.hospital().text.lower()
        assert not any(bad in name for bad in pools.HOSPITAL_BLOCKLIST)


def test_emails_are_well_formed() -> None:
    f = EntityFactory(10)
    pattern = re.compile(r"[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}")
    for _ in range(N):
        p = f.person() if f.rng.random() < 0.8 else None
        assert pattern.fullmatch(f.email(p).text)


def test_addresses_are_single_line_and_varied() -> None:
    f = EntityFactory(11)
    values = [f.address() for _ in range(N)]
    assert all("\n" not in v.text for v in values)
    assert len({v.text for v in values}) > 0.9 * N
    assert {v.fmt for v in values} >= {"intl", "pk_house_street", "pk_flat", "pk_locality"}


def test_format_coverage_over_many_draws() -> None:
    f = EntityFactory(12)
    assert len(Counter(f.phone().fmt for _ in range(N))) >= 15
    assert len(Counter(f.record_id().fmt for _ in range(N))) == 11
    assert len(Counter(f.date().fmt for _ in range(N))) == len(DATE_FORMATS)
