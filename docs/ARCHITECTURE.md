# Architecture

## System overview

```
                 ┌──────────────────────────── DATA ─────────────────────────────┐
 Faker + PK/intl │ Generator (template families, styles, formats) ─┐             │
 name lists  ───►│ LLM-written OOD notes + manual verification ────┼─► Span JSONL│
                 │ Validator: offsets, overlaps, dupes, near-dupes,│             │
                 │ cross-split leakage, statistics                 │             │
                 └───────────────┬─────────────────────────────────┴─────────────┘
                                 │  train / dev / test-ID / test-OOD (frozen, hashed)
          ┌──────────────┬───────┴───────┬──────────────┐
          ▼              ▼               ▼              ▼
      Regex/Rules    Presidio        Transformer     Qwen3-4B (Ollama,
                     (custom         token classif.  JSON schema,
                     recognizers)    (span ← BIO)    string → offset)
          └──────┬───────┴───────┬───────┘              │
                 ▼               ▼                      ▼
       Common interface: Detector.detect(text) -> list[Span]
                 │
                 ▼
       Hybrid fusion (rules derived from dev-set error analysis)
                 │
                 ├──► Evaluator: strict / boundary / partial / type-agnostic matching,
                 │    per-type P/R/F1, leak rate, bootstrap CIs, latency, memory
                 ▼
       Redaction engine (mask / label / consistent surrogate)
                 │
       FastAPI (/detect, /redact, /compare, /health — no input logging)
                 │
       React + TypeScript UI (highlighting, comparison, dashboards)
                 │
       Docker → Hugging Face Spaces · model on HF Hub · optional transformers.js ONNX mode
```

## Components

| Component | Module | Status |
|---|---|---|
| Data contracts (`Span`, `Document`, `EntityType`) | `privymed.schema` | IMPLEMENTED (M1) |
| Detector interface | `privymed.detectors.base` | IMPLEMENTED (M1) |
| JSONL I/O | `privymed.io` | IMPLEMENTED (M1) |
| Config / logging / seeding | `privymed.config`, `logging_utils`, `repro` | IMPLEMENTED (M1) |
| Synthetic generator + validator | `privymed.data_generation` | NOT IMPLEMENTED |
| Regex baseline | `privymed.detectors.regex` | NOT IMPLEMENTED |
| Presidio baseline | `privymed.detectors.presidio` | NOT IMPLEMENTED |
| Span evaluator | `privymed.evaluation` | NOT IMPLEMENTED |
| Transformer training / inference | `privymed.training`, `privymed.detectors.transformer` | NOT IMPLEMENTED |
| LLM baseline | `privymed.detectors.llm` | NOT IMPLEMENTED |
| Hybrid | `privymed.hybrid` | NOT IMPLEMENTED |
| Redaction | `privymed.redaction` | NOT IMPLEMENTED |
| ONNX optimisation | `privymed.optimization` | NOT IMPLEMENTED |
| API / frontend / deployment | `privymed.api`, `frontend/`, `deployment/` | NOT IMPLEMENTED |

## Architecture Decision Records

### ADR-001 — Character spans are the source of truth
- **Decision:** gold annotations and all predictions are half-open character intervals `[start, end)` with a label.
- **Why:** regex, Presidio and the LLM natively produce character spans; the transformer produces token tags. Evaluating everything in tag space would inject tokenizer artifacts and make comparison unfair.
- **Alternatives:** BIO tags as the source of truth (simple for seqeval, but tokenizer-dependent); token-level labels (hides boundary errors).
- **Trade-off:** we must write and test our own span evaluator; we cross-check it against seqeval for the transformer.
- **Details:** offsets are Unicode code-point indices into the original (un-normalised) text. Matching uses `Span.key` / `Span.range`, not object equality, because predictions carry `score` and `source`.

### ADR-002 — 9-type schema
- **Decision:** PATIENT, STAFF, DATE, PHONE, EMAIL, CNIC, ID, ADDRESS, HOSPITAL.
- **Why:** `OTHER_PII` has no consistent annotation definition. Splitting names into PATIENT vs STAFF creates the one distinction that requires context, which is where learned models should beat rules. MRNs and patient IDs merged into ID because they are not reliably distinguishable by surface form. CNIC kept separate because of its fixed 5-7-1 structure.
- **Trade-off:** PATIENT/STAFF confusion will lower typed F1; the type-agnostic (redaction) metric will show whether it matters for privacy.

### ADR-003 — Three-tier test data
- **Decision:** test-ID (held-out template families from our generator), test-OOD (notes written by a different process — an LLM — and manually verified), optional external synthetic PII dataset.
- **Why:** with a single generator, rules and the model are evaluated on the distribution they were designed for, inflating scores. The ID/OOD gap is the scientifically interesting result.

- **Protocol (Milestone 2 review, finding M2-8):** test-ID shares *formats* with train by design (every phone/ID/date format in test also occurs in train). It is therefore an **in-format** benchmark: it measures generalisation to unseen *document structures*, not to unseen *formats*. Regex/Presidio rules and LLM prompts must be written from the annotation guide plus train/dev observations and error analysis on dev only; they must never be tuned on test-ID. Robustness to unseen formats is measured on test-OOD.

### ADR-007 — Milestone 2 review outcomes (shortcuts and leakage)
- **Title shortcut removed:** staff titles are randomised at render time (Dr./Dr/none/Prof./Mr./Ms.); ~4% of patient titles are "Dr.". STAFF-after-"Dr" fell from 70/100/82% (train/dev/test) to 46/66/53%; PATIENT-after-"Dr" rose from 0% to 0.2–0.5%.
- **Leak detection:** the validator checks every document's families against the manifest and runs a *structural* near-duplicate check (entities → `<LABEL>`, digits → `0`, 3-word shingles, threshold 0.25). The threshold is calibrated: same-family nearest-neighbour p05 = 0.28, different-family max = 0.17. A simulated leak of 50 test-family documents into train is caught by both checks (regression test). The original raw-text check at 0.8 missed it.
- **Memorisation reported at token level:** 71–80% of PATIENT/STAFF name tokens in eval splits also occur in train (whole-string: 17–26%). Name pools are deliberately not split (realism); M8 will report an "entities unseen in train" slice.
- **Per-type floor:** every split's estimated share of each entity type ≥ 2.5%. Measured ceiling with the current families is ~3.2% (EMAIL/CNIC are the bottleneck); dev still has only ~3% ID spans. Documented limitation; more EMAIL/CNIC-bearing families would raise the ceiling.

### ADR-004 — Gold spans must not overlap or carry boundary whitespace
- Enforced in `Document` validation so generator bugs fail loudly rather than silently corrupting training labels.

### ADR-006 — Family-level, constrained random splits with frozen manifests
- **Decision:** the split unit is the template family. Assignment is a seeded random draw under explicit constraints: one family held out per document type with ≥3 families (two if ≥4), alternating test/dev; one entity-free family per split; train keeps every document type; every split contains all 9 entity types (verified by rendering; the attempt count is recorded). Bundles combine only same-split families.
- **Why:** document-level random splits leak template structure into test and inflate every system's scores. A hand-picked assignment would invite "did you choose easy test families?"; a constrained seeded draw is auditable.
- **Freezing:** `privymed-generate` writes a manifest (`data/manifests/<version>.json`, committed) with per-file SHA-256, config, split assignment, git commit and Faker version, and refuses to run from uncommitted code. `verify_manifest()` must pass before any final test evaluation.
- **Trade-off:** test-ID covers only the document types that had a held-out family; scores are lower than a random split would give, but honest.

### ADR-005 — Tooling
- **uv** for environment/dependency management (fast, lockfile, reproducible). Heavy dependencies added per milestone as dependency groups.
- **Vite + React + TypeScript** rather than Next.js: no SSR need; the static build is served by FastAPI from one container.
- **Ollama** for the local LLM: CUDA builds of llama.cpp are painful on Windows; Ollama supports JSON-schema structured output.

## References (to be verified when cited in the report)

- Stubbs, Kotfila & Uzuner (2015). 2014 i2b2/UTHealth de-identification shared task. *JBI*. https://doi.org/10.1016/j.jbi.2015.06.007
- Dernoncourt et al. (2017). De-identification of patient notes with recurrent neural networks. *JAMIA*. https://doi.org/10.1093/jamia/ocw156
- Johnson, Bulgarelli & Pollard (2020). De-identification of free-text medical records using pre-trained bidirectional transformers. *CHIL*. https://doi.org/10.1145/3368555.3384455
- Norgeot et al. (2020). Protected Health Information filter (Philter). *npj Digital Medicine*. https://doi.org/10.1038/s41746-020-0258-y
- Microsoft Presidio documentation. https://microsoft.github.io/presidio/
