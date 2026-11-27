# Experiments log

Every **result** entry is produced by a committed script and points to its report in `reports/`. Development iterations measured with an uncommitted scratch loop are marked as such: they explain how the system was built but are not reproducible from a commit.

All results below are on **dev** (dataset v1). Test splits are untouched until Milestone 8.

## Corrections after the Milestone 3 review (2026-11-27)

The independent review found that **9 rule cues occurred 0 times in train/dev**, and 5 of them came from templates of test_id families ("Prescriber", "Rx No", "Lab No", "Booking reference", "Booked for"). The generator's author also wrote the rules, which is how test-template wording leaked in. It broke CLAUDE.md rule 3 for both baselines (Presidio shared the cues). The cues were removed, all cues moved to `detectors/cues.py`, and `tests/test_cues.py` now fails the build if any cue is absent from train/dev. The review also found that Presidio's boundary normalisation stripped "(" from parenthesised phones, handicapping Presidio.

E-001 and E-002 below were **re-run from clean commit `a5c620b`** (reports record `git.dirty = false`). The original numbers (commits `fb8f068`, `5a218cd`) are kept in each entry for the record. Dev numbers barely change because dev never contained the leaked cues; their effect would have appeared on test_id.

## E-001 — Regex baseline (`regex`), dataset v1 / dev

- **Date:** 2026-11-27 · **Commit:** `a5c620b` (re-run after review; original `fb8f068`) · **Report:** `reports/eval/regex_v1_dev.json`
- **Command:** `uv run privymed-eval --system regex --split dev`
- **Hardware:** CPU only (Ryzen 7 170), single thread

| Mode | Precision | Recall | F1 [95% CI] | Macro F1 |
|---|---:|---:|---|---:|
| strict | 0.998 | 0.963 | 0.980 [0.975, 0.984] | 0.982 |
| boundary | 0.999 | 0.964 | 0.981 [0.977, 0.985] | 0.983 |
| partial | 0.999 | 0.963 | 0.981 [0.976, 0.984] | 0.983 |
| overlap | 1.000 | 0.965 | 0.982 [0.978, 0.986] | 0.984 |

- **Leak rate:** 2.30% of gold PII characters uncovered.
- **Latency:** 0.38 ms/doc p50, 1.03 ms p95 (single run; see EVALUATION.md on latency variance).
- **Original (pre-review, `fb8f068`):** strict F1 0.979 [0.975, 0.983], leak 2.34%. Included 9 cues absent from train/dev (5 from test templates).

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

- **Date:** 2026-11-27 · **Commit:** `a5c620b` (re-run after review; original `5a218cd`) · **Reports:** `reports/eval/presidio_v1_dev.json`, `reports/eval/presidio_sweep_score_threshold_dev.json`
- **Commands:** `uv run privymed-eval --system presidio --split dev --sweep score_threshold=0.3,0.4,0.5,0.6,0.7`, then a default run (0.3 is now the detector default)
- **Configuration:** presidio-analyzer 2.2.362, spaCy `en_core_web_lg` 3.8.0, phone regions PK/GB/US, custom `PK_CNIC` and `RECORD_ID` recognizers, schema mapping and guide normalisation (see `src/privymed/detectors/presidio.py`).

### Threshold sweep (dev, strict micro)

| score_threshold | P | R | F1 | Leak |
|---:|---:|---:|---:|---:|
| 0.3 | 0.704 | 0.759 | **0.731** | 13.48% |
| 0.4 | 0.704 | 0.759 | 0.731 | 13.48% |
| 0.5 | 0.663 | 0.658 | 0.660 | 21.28% |
| 0.6 | 0.663 | 0.657 | 0.660 | 21.29% |
| 0.7 | 0.642 | 0.601 | 0.621 | 24.91% |

Selected 0.3 (tie with 0.4; rule: tie → lower threshold). No scores fall between 0.3 and 0.4 (spaCy NER results are fixed at 0.85; pattern results start at 0.4; thresholds 0.0–0.2 also give identical results). At ≥ 0.5 only context-boosted phones (0.75) survive, so PHONE recall falls sharply; at 0.7 every record ID is dropped, because the custom RECORD_ID recognizer is never context-boosted (configuration artefact, disclosed).

### Result at score_threshold = 0.3

| Mode | Precision | Recall | F1 [95% CI] | Macro F1 |
|---|---:|---:|---|---:|
| strict | 0.704 | 0.759 | 0.731 [0.722, 0.740] | 0.748 |
| boundary | 0.722 | 0.778 | 0.749 [0.740, 0.758] | 0.761 |
| partial | 0.837 | 0.903 | 0.869 [0.862, 0.875] | 0.891 |
| overlap | 0.870 | 0.938 | 0.903 [0.898, 0.907] | 0.916 |

- **Leak rate:** 13.48%. **Latency:** 24.9 ms/doc p50, 63.6 ms p95 (CPU, single run).
- **Original (pre-review, `5a218cd`):** strict F1 0.722 [0.713, 0.732], leak 13.54%; PHONE strict F1 0.917 because "(" was stripped from parenthesised phones (now 0.980).

Per-type F1 by mode (strict / partial / overlap): PATIENT 0.529 / 0.745 / 0.841 · STAFF 0.693 / 0.922 / 0.988 · DATE 0.890 / 0.951 / 0.953 · PHONE 0.980 / 0.980 / 0.980 · ADDRESS 0.000 / 0.703 / 0.714 · HOSPITAL 0.660 / 0.733 / 0.781 · EMAIL, CNIC 1.000 · ID 0.983 (strict).

### Interpretation

- **Detection vs boundaries.** Presidio *finds* most names (STAFF overlap F1 0.988) but its boundaries differ from the annotation guide (strict 0.693). Reporting only strict F1 would understate its detection ability; reporting only overlap would hide that its spans do not match the schema.
- **ADDRESS = 0.000 strict** is a capability gap, not a bug: Presidio has no postal-address entity, and spaCy `LOCATION` covers city/area fragments of an address. The regex address rules were deliberately not added to Presidio.
- **Shared logic (disclosed).** Presidio's ID recognizer and its STAFF/PATIENT split use the same cue lists and ID shapes as the regex baseline (`detectors/cues.py`), because Presidio has no record-number or clinical-role concept. Name, date, phone, hospital and address detection are Presidio/spaCy only.
- **Default-configuration failures fixed by configuration** (smoke test before E-002): phone and MRN tagged DATE by spaCy, "CNIC"/"MRN" tagged ORGANIZATION, US driver-licence and URL noise. See ADR in the detector docstring.
- Compared with E-001 (regex), Presidio leaks ~6× more PII characters on dev (13.5% vs 2.3%) and is roughly 60× slower (single-run latency). Both are dev numbers; regex was tuned on dev for three iterations, Presidio only by threshold.
