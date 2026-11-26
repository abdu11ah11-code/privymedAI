# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added — Milestone 2 (in progress)
- 2.1 `EntityFactory`: seeded generators for all 9 entity types with per-value format tags; annotation guide.
- 2.2 Template engine (`TextBuilder`, `NoteContext`, `TemplateFamily`, `generate_document`): labels correct by construction, consistent per-note cast, DOB/age/date-order coherence, non-annotated distractor fillers, SHA-256 per-document seeds.
- `Span.fmt` optional field carrying the gold surface-format tag.

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
