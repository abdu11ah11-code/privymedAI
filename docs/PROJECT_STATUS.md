# Project status

_Last updated: 2026-11-27 (end of Milestone 3)_

## Environment
- Windows 11 Pro · Ryzen 7 170 (8C/16T) · 15.3 GB RAM · RTX 4050 Laptop 6 GB (driver 591.62, CUDA 13.1 capable) · 145 GB free
- Python 3.12.10 (uv 0.13.10) · Git 2.56.1 · Node 26.13.1 · GitHub CLI 2.106.0 (not logged in; git pushes via Git Credential Manager)
- Repository: https://github.com/abdu11ah11-code/privymedAI

## Completed
- **Milestone 0** — architecture and roadmap approved.
- **Milestone 1** — foundation: uv project, `Span`/`Document`/`Detector` contracts, I/O, config, tests, docs.
- **Milestone 2** — synthetic dataset engine, **v1 frozen**:
  - 29 template families (26 with PII across 9 document types, 3 entity-free), entity factory with format tags, offset-safe noise, same-patient bundles, hard cases.
  - Family-level constrained splits; per-split hospital/narrative pools; manifest with SHA-256.
  - `privymed-validate`: shape, BIO, duplicates (raw + structural), family-leak, identifier overlap, title shortcut stats.
  - Independent review: 0 critical, 5 important, 8 minor — all addressed (ADR-007).
- **Milestone 3** — evaluator and baselines:
  - `privymed.evaluation`: strict / boundary / partial / overlap, maximum-cardinality matching, leak rate, bootstrap CIs; seqeval cross-check (docs/EVALUATION.md).
  - `privymed-eval`: manifest verification, test-split allowlist + hash guard, dev-only sweeps, provenance (git dirty state, packages).
  - Baselines on **dev** (E-001, E-002, clean commit `a5c620b`): regex strict F1 0.980 [0.975, 0.984], leak 2.30%, ~0.4 ms/doc; Presidio strict F1 0.731 [0.722, 0.740], overlap 0.903, leak 13.48%, ~25 ms/doc.
  - Independent review: 1 critical (9 rule cues absent from train/dev, 5 from test templates — removed, now lint-tested), 5 important, minors — all fixed.

## Dataset status — v1 (frozen)
| Split | Docs | Spans | Families | SHA-256 (prefix) |
|---|---:|---:|---|---|
| train | 4000 | 44,747 | 19 | `ebbc51e340de` |
| dev | 600 | 6,835 | 5 | `f24482a85a49` |
| test_id | 1000 | 12,924 | 5 | `86edd0d5032c` |

- Generated from commit `03e0263` (clean tree). Manifest: `data/manifests/v1.json`. Report: `reports/data/v1_report.md`.
- Validation: **0 errors, 0 warnings**. Max structural similarity eval vs train: 0.088 (leak threshold 0.25).
- Regenerate: `uv run privymed-generate --config configs/data_v1.yaml` (byte-identical; verified twice).
- Test-OOD set: NOT IMPLEMENTED (Milestone 2b).

## Known limitations (documented, not bugs)
- Test-ID is an *in-format* benchmark: all test formats occur in train (ADR-003 protocol).
- 71–80% of eval name *tokens* occur in train (whole strings 17–26%); name pools are not split.
- Per-type mix differs across splits; dev has ~3% ID spans (floor 2.5%; ceiling ~3.2% with current families).
- Mean document length ~80 words; subword token counts to be measured in M4.
- Ages > 89 are not annotated (out of schema).

## Tests
- 572 passed, 3 skipped (entity-free families exempt from the ≥3-types rule). ruff + mypy --strict clean.

## Model status
- Baselines evaluated on dev only (regex, Presidio). No learned models trained yet. Test splits untouched.

## Deployment status
- NOT IMPLEMENTED.

## Next task
- **Milestone 2b:** test-OOD set — LLM-written notes, pre-labelled by the baselines, corrected by hand. Requires Ollama + a Qwen model (~3 GB).
- **Milestone 4:** BERT-family token classifier training on train, model selection on dev.
