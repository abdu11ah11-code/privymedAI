"""Regex baseline: positives from the annotation guide, and hard negatives that must stay O."""

from __future__ import annotations

import pytest

from privymed.detectors.regex import RegexDetector
from privymed.schema import EntityType

E = EntityType
DET = RegexDetector()


def found(text: str) -> list[tuple[str, EntityType]]:
    return [(text[s.start : s.end], s.label) for s in DET.detect(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Email: ali.khan92@gmail.com", ("ali.khan92@gmail.com", E.EMAIL)),
        ("CNIC 35202-1234567-1 on file", ("35202-1234567-1", E.CNIC)),
        ("CNIC 3520212345671.", ("3520212345671", E.CNIC)),
        ("Call 0300-1234567 today", ("0300-1234567", E.PHONE)),
        ("Mobile: +92 333 1234567", ("+92 333 1234567", E.PHONE)),
        ("Tel: (042) 35761234", ("(042) 35761234", E.PHONE)),
        ("Seen on 12/03/2024.", ("12/03/2024", E.DATE)),
        ("DOB 2nd March 1990", ("2nd March 1990", E.DATE)),
        ("Admitted March 5, 2026", ("March 5, 2026", E.DATE)),
        ("MRN: 7159-0324-03", ("7159-0324-03", E.ID)),  # guide: field label excluded
        ("ID MRN-2024-001234", ("MRN-2024-001234", E.ID)),  # guide: internal prefix included
        ("Referred to Crescent Medical Centre today", ("Crescent Medical Centre", E.HOSPITAL)),
        (
            "House No. 12, Street 4, Model Town, Lahore",
            ("House No. 12, Street 4, Model Town, Lahore", E.ADDRESS),
        ),
        ("Seen by Dr. Imran Khan, MBBS", ("Imran Khan", E.STAFF)),  # guide: title excluded
        ("Patient: Ayesha Siddiqui\nCNIC: x", ("Ayesha Siddiqui", E.PATIENT)),
        ("- Name: Rogers, Robert", ("Rogers, Robert", E.PATIENT)),
    ],
)
def test_detects_guide_examples(text: str, expected: tuple[str, EntityType]) -> None:
    assert expected in found(text)


@pytest.mark.parametrize(
    "text",
    [
        "Frank blood was not seen on rectal examination.",
        "Bell's palsy was considered and excluded.",
        "Escalate if BP is below 90/60 or saturation below 92%.",
        "Reference ranges: haemoglobin 12.0-16.0 g/dL, WBC 4.0-11.0 x10^9/L.",
        "Version 2.1 - reviewed annually. Ward 4 visiting time is after 5:30 PM.",
        "Clinic hours: 8:00 AM - 2:00 PM, Monday to Saturday.",
        "May require admission if symptoms worsen.",
        "Pain since yesterday; review in two weeks.",
        "Take Metformin 500 mg twice daily for 10 days.",
    ],
)
def test_hard_negatives_produce_nothing(text: str) -> None:
    assert found(text) == []


def test_names_do_not_cross_lines_or_space_runs() -> None:
    # Dev iterations 1 and 2: these used to swallow the next field label.
    assert ("Tahir Durrani", E.PATIENT) in found("Full Name: Tahir Durrani\nCNIC: 1")
    assert ("Kimberly Lloyd", E.STAFF) in found("Referring doctor: Dr. Kimberly Lloyd   Contact: 1")


def test_title_after_role_cue_is_not_the_name() -> None:
    assert found("Clinician: Ms. Warda Sethi") == [("Warda Sethi", E.STAFF)]


def test_overlap_resolution_prefers_structured_types() -> None:
    # An email contains name-like text; the EMAIL span must win and nothing may overlap it.
    spans = DET.detect("Contact: Mr. Ali ali.khan@gmail.com")
    assert all(not a.overlaps(b) for i, a in enumerate(spans) for b in spans[i + 1 :])
    assert any(s.label is E.EMAIL for s in spans)


def test_predictions_are_stamped_and_trimmed() -> None:
    spans = DET.detect("Phone: 0300-1234567.")
    assert [s.source for s in spans] == ["regex"]
    assert "Phone: 0300-1234567."[spans[0].start : spans[0].end] == "0300-1234567"
