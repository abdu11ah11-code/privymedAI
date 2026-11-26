# CLAUDE.md — PrivyMed project instructions

PrivyMed is a research prototype for de-identifying **synthetic** clinical-style text. It compares regex rules, Microsoft Presidio, a fine-tuned transformer, a local Qwen LLM and a hybrid system on a shared benchmark. The owner is building it as a portfolio project and must be able to explain every decision — explain concepts, don't just emit code.

## Non-negotiable rules

1. **Never invent results.** No metric, timing, size or dataset statistic appears in docs unless produced by a committed script; label anything else NOT MEASURED / NOT IMPLEMENTED / NOT VERIFIED.
2. **Synthetic data only.** Never add real patient data or real people's PII.
3. **The test sets are frozen.** Tune thresholds, prompts, fusion rules and checkpoints on `dev` only. Test is run once, at Milestone 8, by the final-evaluation script.
4. **Never log raw document text or span surface strings** at INFO or above; log ids, counts, offsets.
5. **No compliance claims** (HIPAA, GDPR, clinical certification).
6. Never commit secrets, generated datasets, or model weights (see `.gitignore`).

## Architecture invariants

- Character-offset `Span`s (`src/privymed/schema.py`) are the single source of truth for gold and predictions. BIO tags are derived only for transformer training.
- Every detection system subclasses `privymed.detectors.base.Detector` and implements `_detect(text) -> list[Span]`.
- Gold `Document`s: spans in bounds, non-overlapping, no leading/trailing whitespace or zero-width chars.
- Offsets are Python `str` indices (Unicode code points) into the **original** text — never into a normalised copy. The frontend converts to UTF-16.
- Compare spans with `span.key` (start, end, label) or `span.range`, **never `==`** (equality includes score/source).
- Modify documents with `Document.with_spans(...)`, never `model_copy(update=...)` / `model_construct` (they skip validation).
- `Detector.detect` stamps `source = Detector.name`; every concrete detector must define `name`.
- Generation code must not depend on `set` iteration order (PYTHONHASHSEED can't be fixed at runtime); iterate sorted lists. Seed Faker explicitly.
- `write_documents` is atomic and rejects duplicate `doc_id`s.
- Data splits are by **template family**, not by random document, to prevent leakage.

## Environment (Windows 11, PowerShell 5.1)

- Python 3.12 managed by **uv**. Run everything via `uv run ...`.
- GPU: RTX 4050 Laptop, 6 GB VRAM. Keep training configs within that budget (fp16, base-size models).
- In a fresh shell, refresh PATH if tools aren't found:
  `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`

## Verification before every commit

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Workflow per milestone

PLAN → IMPLEMENT (small steps) → TEST → REVIEW (separate reviewer agent) → DOCUMENT (update `docs/PROJECT_STATUS.md`, `docs/ROADMAP.md`, `CHANGELOG.md`, `docs/EXPERIMENTS.md` when relevant) → COMMIT → PUSH to `origin main`.

## Layout

- `src/privymed/` — package (schema, io, config, detectors/, later: data_generation/, evaluation/, training/, hybrid/, redaction/, api/)
- `configs/` — YAML configs
- `tests/` — pytest
- `docs/` — architecture, roadmap, experiments, status
- `data/`, `models/`, `reports/` — generated artifacts (mostly git-ignored)
