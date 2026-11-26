# Roadmap

Status values: NOT STARTED · IN PROGRESS · DONE (verified) · BLOCKED

| # | Milestone | Status | Completion criteria (quality gate) |
|---|---|---|---|
| 0 | Feasibility & architecture | DONE | Architecture approved by owner (2026-11-26) |
| 1 | Foundation | IN PROGRESS | git + GitHub remote, uv env, schema + Detector interface, tests/ruff/mypy pass, docs skeleton |
| 2 | Synthetic dataset engine | NOT STARTED | ≥15 template families, ≥8 doc types, validator 0 errors, family-level splits, leakage check passes, stats report |
| 2b | OOD test set | NOT STARTED | 150–300 LLM-written notes, every annotation manually verified |
| 3 | Baselines + span evaluator | NOT STARTED | Regex + Presidio implement `Detector`; evaluator matches hand-computed cases; seqeval cross-check |
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
- [ ] 2.3 ~20 template families across 9 document types + template lint tests
- [ ] 2.4 Hard cases (entity-free notes, adjacency, name/word ambiguity, role swaps)
- [ ] 2.5 Family-level splits + hashed manifests
- [ ] 2.6 Validator + statistics report + near-duplicate / leakage checks
- [ ] Independent review → commit → push
