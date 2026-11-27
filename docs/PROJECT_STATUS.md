# Project status

_Last updated: 2026-11-28 (end of Milestone 5)_

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

- **Milestone 4** — transformer token classifiers (dev only):
  - 3 models × 3 seeds on the RTX 4050 (bf16 training, fp32 master weights, fp32 inference). Dev strict F1: DistilBERT 0.9118 ± 0.0108, RoBERTa 0.9852 ± 0.0036, DeBERTa-v3 0.9931 ± 0.0069.
  - **RoBERTa primary** (`roberta_s7`, median seed: dev strict F1 0.984, 13 leaked characters in 9 of 600 docs), **DeBERTa pre-registered accuracy variant** (`deberta_s42`), in `configs/selected_models.yaml`.
  - Independent review: 0 critical, 3 important, 9 minor — all fixed; RoBERTa retrained after the merged-prefix label fix.

- **Milestone 5** — local LLM baseline (dev only): Qwen 3.5 4B via Ollama, prompt v2 (official), strict F1 0.959, leak 2.49% (comparable to regex 2.30%), 0 parse failures, 18/6,550 hallucinated mentions, ~4.5 s/doc. Independent review: 0 critical, 4 important, 7 minor — all addressed.

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
- 626 passed, 3 skipped (entity-free families exempt from the ≥3-types rule). ruff + mypy --strict clean.

## Model status
- Regex, Presidio, 9 transformer checkpoints and the Qwen LLM evaluated on dev only. Checkpoints in `models/` (git-ignored; reproducible with `bash scripts/run_m4_grid.sh`). Test splits untouched.

## Deployment status
- NOT IMPLEMENTED.

## Next task
- **Milestone 2b:** test-OOD set — Qwen-written notes in unseen styles, pre-labelled by regex/Presidio/RoBERTa, corrected by the owner (~1–2 h of hand-checking; show disagreements, measure agreement on a from-scratch sample).
- Then **Milestone 6:** error analysis on dev → hybrid system.
