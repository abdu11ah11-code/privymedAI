# Roadmap

Status values: NOT STARTED · IN PROGRESS · DONE (verified) · BLOCKED

| # | Milestone | Status | Completion criteria (quality gate) |
|---|---|---|---|
| 0 | Feasibility & architecture | DONE | Architecture approved by owner (2026-11-26) |
| 1 | Foundation | DONE | git + GitHub remote, uv env, schema + Detector interface, tests/ruff/mypy pass, docs skeleton |
| 2 | Synthetic dataset engine | DONE (v1 frozen) | ≥15 template families, ≥8 doc types, validator 0 errors, family-level splits, leakage check passes, stats report |
| 2b | OOD test set | NOT STARTED | 150–300 LLM-written notes, every annotation manually verified |
| 3 | Baselines + span evaluator | DONE | Regex + Presidio implement `Detector`; evaluator matches hand-computed cases; seqeval cross-check |
| 4 | Transformer training | NOT STARTED | 3 candidates × 3 seeds on dev; checkpoint reload reproduces dev score; experiments logged |
| 5 | Qwen LLM baseline | NOT STARTED | Prompt + schema documented; parse/hallucination failures counted; same docs and evaluator |
| 6 | Error analysis → hybrid | NOT STARTED | Error taxonomy on dev; each fusion rule justified by a dev finding; ablations |
| 7 | Redaction engine | NOT STARTED | Mask / label / surrogate modes; non-PII text preserved byte-for-byte (property tests) |
| 8 | Frozen final test evaluation | NOT STARTED | One-shot run, test hash logged, bootstrap CIs, all systems same data |
| 9 | ONNX optimisation | NOT STARTED | Size / latency p50,p95 / memory / F1 delta measured; browser feasibility measured |
| 10 | Web application | NOT STARTED | FastAPI + React features working; API tests; no input logging |
| 11 | Deployment | NOT STARTED | Live HF Space verified; model on HF Hub; health check; disclaimer |
| 12 | Portfolio completion | NOT STARTED | README, report, screenshots, resume bullets, interview prep — every number traceable to a results file |

## Milestone 1 tasks

- [x] Install toolchain (Git, uv, Node LTS, GitHub CLI)
- [x] `git init`, noreply commit identity
- [x] `pyproject.toml`, uv environment, dev tooling (pytest, ruff, mypy)
- [x] `Span` / `Document` / `EntityType` contracts with validation
- [x] `Detector` base class
- [x] JSONL I/O, config loader, logging, seeding
- [x] Tests
- [x] Docs skeleton + CLAUDE.md
- [x] Independent review (0 critical, 7 important, 8 minor; all important + minor fixed except Document hashability — not needed)
- [x] First commit
- [x] GitHub remote + push (github.com/abdu11ah11-code/privymedAI)

## Milestone 2 tasks

- [x] 2.1 Entity value generators (`EntityFactory`) + annotation guide
- [x] 2.2 Template engine: offsets recorded at build time, per-note cast consistency, choice/optional syntax, per-document seeds
- [x] 2.3 24 template families across 9 document types + template lint tests
- [x] 2.4 Hard cases + length/balance fixes
  - Added: narrative paragraphs, same-patient bundles, contact-heavy families, CSV adjacency,
    2 entity-free families, ambiguous names (~5%/name part), shared doctor/patient surnames (8%),
    offset-safe noise on an independent RNG (every noisy doc has an exact clean twin).
  - Measured (3,000 docs, 30% bundles): mean 80 words (was 48), CNIC/EMAIL/ADDRESS 3.6/3.9/4.0%
    (was 2.5/2.9/3.2%), entity-free 5.1%.
  - Open: length still below the 150–400 token target in words; measure real subword token
    counts in M4 and set bundle ratio/size as a 2.5 config parameter.
- [x] 2.5 Family-level splits + hashed manifests (`privymed-generate`, `verify_manifest`, clean-tree guard)
  - Prototype (200 docs, split_seed 7): valid assignment on attempt 4; test-ID families =
    appt_booking, dis_letter, lab_table, rx_label, protocol_note; all 9 types in every split.
  - v1 (4000/600/1000) will be generated and its manifest committed **after** 2.6 validation passes.
- [x] 2.6 Validator + statistics report + near-duplicate / leakage checks (`privymed-validate`)
  - Full-size trial build: 0 errors. Validator exposed HOSPITAL memorisation (93.7% of test
    strings seen in train) → per-split hospital cores + narrative pools → 0.6%. Entity-free share
    equalised via `entity_free_ratio` (was 3.8/13.2/14.6%, now 6.7/4.7/5.8%).
  - Documented limitations: per-type mix differs across splits (family composition; dev has ~200
    IDs); 17–26% of eval PATIENT/STAFF whole strings and **71–80% of their tokens** also occur in
    train (finite name pools; see ADR-007).
- [x] Independent review: 0 critical, 5 important, 8 minor — all addressed (ADR-007), with
  regression tests in `tests/test_review_m2.py` (incl. the reviewer's simulated family leak).
- [x] Freeze v1 from a clean tree (commit `03e0263`) → validate (0 errors, 0 warnings) → manifest + report committed

## Milestone 3 tasks

- [x] 3.1 Span evaluator: strict / boundary / partial / overlap, leak rate, bootstrap CIs; seqeval cross-check (docs/EVALUATION.md)
- [x] 3.2 Regex baseline — dev strict F1 0.980, leak 2.30% (E-001; tuned 3 iterations on dev)
- [x] 3.3 Presidio baseline — dev strict F1 0.731, overlap 0.903, leak 13.48% (E-002)
- [x] 3.4 `privymed-eval` runner: manifest check, test-split guard, dev-only sweeps, latency
- [x] Independent review: 1 critical (test-template cues leaked into rules), 5 important, minors — all fixed; E-001/E-002 re-run from clean commit `a5c620b`
