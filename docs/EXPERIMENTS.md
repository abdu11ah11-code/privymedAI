# Experiments log

Every **result** entry is produced by a committed script and points to its report in `reports/`. Development iterations measured with an uncommitted scratch loop are marked as such: they explain how the system was built but are not reproducible from a commit.

All results below are on **dev** (dataset v1). Test splits are untouched until Milestone 8.

## E-001 — Regex baseline (`regex`), dataset v1 / dev

- **Date:** 2026-11-27 · **Commit:** `fb8f068` · **Report:** `reports/eval/regex_v1_dev.json`
- **Command:** `uv run privymed-eval --system regex --split dev`
- **Hardware:** CPU only (Ryzen 7 170), single thread

| Mode | Precision | Recall | F1 [95% CI] | Macro F1 |
|---|---:|---:|---|---:|
| strict | 0.998 | 0.962 | 0.979 [0.975, 0.983] | 0.982 |
| boundary | 0.999 | 0.963 | 0.981 [0.977, 0.985] | 0.983 |
| partial | 0.999 | 0.963 | 0.980 [0.976, 0.984] | 0.983 |
| overlap | 1.000 | 0.964 | 0.982 [0.977, 0.986] | 0.984 |

- **Leak rate:** 2.34% of gold PII characters uncovered.
- **Latency:** 0.35 ms/doc p50, 0.96 ms p95.

### Development iterations (scratch loop on dev, uncommitted code — not reproducible)

| Iter | Change, each motivated by dev errors | Dev strict F1 | Leak |
|---|---|---:|---:|
| 0 | Initial rules from the annotation guide | 0.786 | 11.9% |
| 1 | Names may not cross line breaks; form cues require `:`/`=` | 0.931 | 10.1% |
| 2 | Exactly one space between name parts; Mr./Ms. after role cues | 0.964 | 10.1% |
| 3 | Address form-field rule (`Address:`, `ADDR=`) | 0.979 | 2.3% |

### Interpretation and caveats

- **Optimistic estimate.** Rules were tuned for three rounds on dev, whose five families are form-heavy (`Full Name:`, `Patient name:` cues), ideal for context-cue rules. Test-ID uses five *different* families (incl. prose letters), so a drop on test is expected; its size is a result in itself.
- **In-format advantage.** Structured types (DATE/PHONE/EMAIL/CNIC/ID ≈ 0.99–1.00) benefit from test-ID sharing formats with train (ADR-003). Test-OOD will measure unseen formats.
- **Remaining dev errors:** untitled staff in prose (`…with Lyndsay O'Ryan`), staff introduced as `Mr./Ms.` (read as patients), hospital acronyms (`CMC`), lower-cased notes. These need context or meaning, not form.
- A unit test exposed a sentence-final date bug (`Seen on 12/03/2024.`) that dev never exercised. Fixed before E-001.

## E-002 — Presidio baseline (`presidio`), dataset v1 / dev

- **Date:** 2026-11-27 · **Commit:** `5a218cd` · **Reports:** `reports/eval/presidio_v1_dev.json`, `reports/eval/presidio_sweep_score_threshold_dev.json`
- **Commands:** `uv run privymed-eval --system presidio --split dev --sweep score_threshold=0.3,0.4,0.5,0.6,0.7`, then `--param score_threshold=0.3`
- **Configuration:** presidio-analyzer 2.2.362, spaCy `en_core_web_lg` 3.8.0, phone regions PK/GB/US, custom `PK_CNIC` and `RECORD_ID` recognizers, schema mapping and guide normalisation (see `src/privymed/detectors/presidio.py`).

### Threshold sweep (dev, strict micro)

| score_threshold | P | R | F1 | Leak |
|---:|---:|---:|---:|---:|
| 0.3 | 0.696 | 0.750 | **0.722** | 13.54% |
| 0.4 | 0.696 | 0.750 | 0.722 | 13.54% |
| 0.5 | 0.661 | 0.656 | 0.659 | 21.29% |
| 0.6 | 0.661 | 0.656 | 0.659 | 21.31% |
| 0.7 | 0.640 | 0.599 | 0.619 | 24.92% |

Selected 0.3 (tie with 0.4; rule: tie → lower threshold). No scores fall between 0.3 and 0.4: spaCy NER results are fixed at 0.85, pattern results start at 0.4. Thresholds ≥ 0.5 drop phone numbers (base score 0.4).

### Result at score_threshold = 0.3

| Mode | Precision | Recall | F1 [95% CI] | Macro F1 |
|---|---:|---:|---|---:|
| strict | 0.696 | 0.750 | 0.722 [0.713, 0.732] | 0.741 |
| boundary | 0.714 | 0.769 | 0.740 [0.731, 0.750] | 0.755 |
| partial | 0.837 | 0.903 | 0.869 [0.862, 0.875] | 0.891 |
| overlap | 0.870 | 0.938 | 0.903 [0.898, 0.907] | 0.916 |

- **Leak rate:** 13.54%. **Latency:** 20.9 ms/doc p50, 50.6 ms p95 (CPU).

Per-type F1 by mode (strict / partial / overlap): PATIENT 0.529 / 0.745 / 0.841 · STAFF 0.693 / 0.922 / 0.988 · DATE 0.890 / 0.951 / 0.953 · PHONE 0.917 / 0.980 / 0.980 · ADDRESS 0.000 / 0.703 / 0.714 · HOSPITAL 0.660 / 0.733 / 0.781 · EMAIL, CNIC 1.000 · ID 0.983 (strict).

### Interpretation

- **Detection vs boundaries.** Presidio *finds* most names (STAFF overlap F1 0.988) but its boundaries differ from the annotation guide (strict 0.693). Reporting only strict F1 would understate its detection ability; reporting only overlap would hide that its spans do not match the schema.
- **ADDRESS = 0.000 strict** is a capability gap, not a bug: Presidio has no postal-address entity, and spaCy `LOCATION` covers city/area fragments of an address. The regex address rules were deliberately not added to Presidio.
- **Default-configuration failures fixed by configuration** (smoke test before E-002): phone and MRN tagged DATE by spaCy, "CNIC"/"MRN" tagged ORGANIZATION, US driver-licence and URL noise. See ADR in the detector docstring.
- Compared with E-001 (regex), Presidio leaks ~6× more PII characters on dev (13.5% vs 2.3%) and is ~60× slower. Both are dev numbers; regex was tuned on dev for three iterations, Presidio only by threshold.
