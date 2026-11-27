# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added — Milestone 3 (in progress)
- 3.1 `privymed.evaluation`: four matching modes, one-to-one greedy matching, leak rate, document bootstrap CIs; `docs/EVALUATION.md`; seqeval cross-check test.
- 3.2 `RegexDetector` baseline with unit tests for guide examples and hard negatives.
- 3.3 `PresidioDetector` (Presidio + spaCy `en_core_web_lg`) configured for the schema; custom CNIC and record-ID recognizers; `baselines` dependency group.
- 3.4 `privymed-eval` CLI: manifest verification, test-split guard, `--param`, dev-only `--sweep`, latency and throughput reporting.
- Experiments E-001 (regex) and E-002 (Presidio) on dev.

### Added — Milestone 2 (in progress)
- 2.1 `EntityFactory`: seeded generators for all 9 entity types with per-value format tags; annotation guide.
- 2.2 Template engine (`TextBuilder`, `NoteContext`, `TemplateFamily`, `generate_document`): labels correct by construction, consistent per-note cast, DOB/age/date-order coherence, non-annotated distractor fillers, SHA-256 per-document seeds.
- `Span.fmt` optional field carrying the gold surface-format tag.
- 2.3 24 template families over 9 document types (discharge, OPD, referral, prescription, lab, appointment, admission, progress, radiology) in formal, shorthand, form, bullet, prose, SMS, email, table and key-value styles; template lint tests; multi-patient lists; age-plausible relatives.

- 2.4 Hard cases and realism: `generate_bundle` (multi-document same-patient records), entity-free narrative paragraphs, `adm_insurance` / `appt_booking` contact-heavy families, CSV comma-adjacent entities, `edu_leaflet` / `protocol_note` entity-free families, ambiguous word-names, shared doctor/patient surnames, offset-safe noise module (`noise.py`) with per-document profiles on an independent RNG stream.

- 2.5 `dataset.py`: `DataConfig`, constrained seeded family-level split assignment, same-split bundles, `privymed-generate` CLI, SHA-256 manifest with git commit + Faker version, `verify_manifest`, clean-tree guard; `admin_memo` third entity-free family; `configs/data_proto.yaml`, `configs/data_v1.yaml`; ADR-006.

- 2.6 `bio.py` (span↔BIO, alignment errors), `validation.py` + `privymed-validate` (shape rules, BIO round-trip, MinHash near-duplicates, identifier overlap, unseen formats, stats report); per-split hospital-core and narrative pools; `entity_free_ratio`.

### Fixed — Milestone 2 independent review (ADR-007)
- PATIENT/STAFF title shortcut: randomised staff titles at render time, doctor-patients; validator reports title statistics.
- Validator: family-vs-manifest leak check, calibrated structural near-duplicate check (catches a simulated 50-doc leak), doc_id collisions reported instead of crashing, token-level identifier overlap.
- Per-split minimum entity-type share (2.5%) in split assignment.
- Annotation guide: field labels ending in `:`/`=` are never part of ID/CNIC spans.
- Pools: 14 more name-word negatives, 23 more hospital cores, building words disjoint from hospital cores.
- Bundle parts redraw fillers; case noise tagged `+case`; manifest records Python version and `uv.lock` hash; dirty check covers `pyproject.toml`/`uv.lock`.
- Unlabelled-PII regression scan (masked text has no phone/CNIC/email/year shapes).

### Added — Milestone 1
- Milestone 1 foundation: uv-managed Python 3.12 project, `src/` layout package `privymed`.
- Core data contracts: `EntityType` (9-type schema), `Span`, `Document` with gold-annotation validation.
- `Detector` abstract base class — the common interface for all detection systems.
- JSONL document I/O, typed YAML config loader, logging setup, seeding helper.
- Test suite, ruff, mypy (strict) configuration.
- Project documentation: architecture, roadmap, experiments log, project status, CLAUDE.md.

### Fixed (from Milestone 1 independent review)
- `Span.key` / `Span.range` for matching (object equality includes score/source).
- `Detector.detect` stamps `source` with the detector's `name`; `name` enforced on subclasses; fully deterministic sort.
- Strict int offsets; zero-width / BOM characters rejected at span boundaries; whitespace-only spans rejected.
- `Document.with_spans` re-validating copy helper; metadata allows str/int/float/bool.
- Atomic JSONL writes; duplicate `doc_id` detection on read and write.
- Config paths resolve against repo root; seed bounded to 32 bits.
- `repro`: removed ineffective runtime `PYTHONHASHSEED`, added `check_hash_seed`, optional deterministic torch mode, tolerate CUDA DLL `OSError`.
- `.gitignore`: allow-list for `data/`, more weight formats, tracker dirs, secret-file patterns; narrowed over-broad `*token*.txt`.
