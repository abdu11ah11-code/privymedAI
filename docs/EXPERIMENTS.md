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
