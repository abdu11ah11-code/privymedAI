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

## E-003 / E-004 / E-005 — Transformer token classifiers, dataset v1 / dev

- **Date:** 2026-11-27 · **Grid:** `bash scripts/run_m4_grid.sh` (3 models × seeds 13, 42, 7) · **Run records:** `reports/train/<model>_s<seed>.json` · **Official dev scores:** `reports/eval/transformer_v1_dev_<model>_s<seed>.json` (fp32 inference, `privymed-eval`)
- **Commits:** DistilBERT at `c8ed4b8`, DeBERTa at `2982ec7`, RoBERTa retrained at `50bf43e` (after review fix M4-1, below). All records `git.dirty = false`, fp32 master weights. DistilBERT and DeBERTa labels are unaffected by M4-1 (0 merged-prefix tokens), so their runs stand; their checkpoints were re-scored with the fp32 evaluator (difference to the training-time bf16 selection score ≤ 0.0007).
- **Hardware:** RTX 4050 Laptop 6 GB, bf16 autocast for training, fp32 inference. **Training data:** train at max length 512 / stride 64 → 4,034 windows (DistilBERT), 4,018 (RoBERTa), 4,000 (DeBERTa: no train document exceeds 512 DeBERTa tokens, so its windowing path is not exercised). **Selection:** best epoch by dev strict micro F1, at most 4 epochs, patience 2.
- **Hyperparameters:** each model's commonly recommended learning rate (DistilBERT 5e-5, RoBERTa and DeBERTa 3e-5), effective batch 16 (DistilBERT 16×1, RoBERTa 8×2, DeBERTa 4×4 for memory), warmup 10%, weight decay 0.01. Not tuned per model — a fair-but-limited comparison.

| Model | Params | Dev strict F1 (mean ± sample std, n=3) | Dev leak (mean) | False positives (mean) | Best epochs | Train time / run | Peak VRAM | Latency p50 (GPU, 1 doc) |
|---|---:|---|---:|---:|---|---:|---:|---:|
| distilbert-base-cased | 66M | 0.9118 ± 0.0108 | 0.49% | 871 | 4, 4, 4 | 3.7 min | 2.48 GiB | 16 ms |
| roberta-base | 125M | 0.9852 ± 0.0036 | 0.017% | 182 | 3, 2, 3 | 8.6 min | 3.74 GiB | 23 ms |
| microsoft/deberta-v3-base | 184M | 0.9931 ± 0.0069 | 0.020% | 72 | 4, 4, 2 | 22.7 min | 5.37 GiB | 43 ms |

Per seed (13 / 42 / 7): DistilBERT 0.9061 / 0.9050 / 0.9243 · RoBERTa 0.9825 / 0.9892 / 0.9838 · DeBERTa 0.9856 / 0.9945 / 0.9991.

### Model selection (decided with the owner, 2026-11-27)

**Primary: RoBERTa-base, representative checkpoint `roberta_s7`** (median seed). **Pre-registered accuracy variant: DeBERTa-v3-base, `deberta_s42`** (median seed). Both are listed in `configs/selected_models.yaml` *before* any test data is seen, and each will be scored once in Milestone 8.

- Rule stated before the corrected results: if the difference is within seed noise, prefer the more efficient model. DeBERTa − RoBERTa = +0.0079 strict F1, Welch t = 1.77 with n = 3 per model (p ≈ 0.17): not convincing. DeBERTa's worst seed (0.9856) is below RoBERTa's best (0.9892).
- Privacy is tied (leak 0.017% vs 0.020%). DeBERTa's F1 advantage is mostly precision: fewer PATIENT↔STAFF confusions (72 vs 182 false positives).
- RoBERTa is ~2× faster per document, ~2.6× faster to train and 32% smaller (125M vs 184M parameters) — relevant for CPU deployment and ONNX (M9–M11).
- Median seed, not best seed: picking the best seed would be one more act of tuning on dev.
- With n = 3 per model, every stability statement is weak evidence.

### Selected model on dev — `roberta_s7`

Report: `reports/eval/transformer_v1_dev_roberta_s7.json` (commit `50bf43e`).

| Mode | Precision | Recall | F1 [95% CI] |
|---|---:|---:|---|
| strict | 0.972 | 0.996 | 0.984 [0.981, 0.987] |
| boundary | — | — | 0.986 |
| overlap | — | — | 0.988 [0.986, 0.990] |

- **Leak:** 13 of 105,050 gold PII characters uncovered, in 9 of 600 dev documents (0.012%). Regex leaks 2.30% and Presidio 13.48% on the same split.
- **Precision trade-off:** RoBERTa over-redacts more than regex (195 strict false positives vs 15; precision 0.972 vs 0.998). For de-identification this is the cheaper error, but it is an error.
- **Per-type strict F1:** PATIENT 0.993 · STAFF 0.909 · DATE 1.000 · PHONE 1.000 · EMAIL 0.964 · CNIC 1.000 · ID 0.993 · ADDRESS 0.995 · HOSPITAL 0.991. The weak spot is STAFF (role confusion with PATIENT), which also drives most of the seed-to-seed variance for both RoBERTa and DeBERTa.
- **Speed:** 22.8 ms/doc p50 for single-document calls (100-document sample); ~36 docs/s batched throughput (GPU, single run).

### Reproducibility checks

- Inference is fp32 and order/batch invariant: shuffled, reversed, batch-16 and batch-4 inputs change 0 documents (under bf16, 2 dev documents changed — review M4-2).
- A reloaded checkpoint reproduces its training-time dev strict F1 exactly when selection also used fp32 (all three retrained RoBERTa runs).
- Same-seed training is **not** bitwise reproducible on this GPU (deterministic algorithms off): a preliminary DistilBERT seed-13 run gave 0.8994, the grid run 0.9061. Seed-to-seed std is the honest uncertainty measure.

### Problems found and fixed during M4

- **RoBERTa merged-prefix tokens (review M4-1).** Byte-level BPE glues outside characters to an entity's first character (`(+`, `(#`, `=(`, `=#`: 323 tokens in train). They were labelled O, so 322 train spans were unrepresentable and the model was taught to drop a leading `+`/`#`. They are now labelled as the span's first token when the glued characters are ones the guide excludes, and decoding trims them. Gold → labels → windows → decode is exact for all 4,600 train/dev documents with all three tokenizers. Pre-fix RoBERTa records: `reports/train/superseded/` (dev 0.9914 / 0.9901 / 0.9920). Dev contains no merged-prefix cases; after the retrain RoBERTa's dev scores are lower (mean 0.9852), with the differences in PATIENT/STAFF, not in the PHONE/ID types the fix touches. The pre-fix checkpoints were deleted before a per-type comparison was made, so the cause cannot be proven; run-to-run variance in role confusion is the most likely explanation.
- **DeBERTa NaN loss.** Transformers 5 keeps a checkpoint's stored dtype; `deberta-v3-base` is stored in fp16 → fp16 master weights → NaN. Weights now load as fp32 (`load_token_classifier`, behavioural test); a non-finite loss aborts the run.
- **DeBERTa stall.** Batch 8 filled the 6 GB GPU and Windows spilled into system RAM (no epoch in 46 min). Batch 4 × accumulation 4.
- **DeBERTa offsets** include SentencePiece's leading space (fixed by `clean_offsets`).
- **bf16 inference order dependence** (M4-2) → fp32 inference.

### Interpretation and caveats

- On dev, the fine-tuned model leaks far less PII than tuned regex (13 characters in 9 documents vs 2.30% of characters) with no hand-written rules, at the cost of more over-redaction.
- **Epoch cap confound (review M4-3).** 5 of 9 runs reached their best dev score at the 4-epoch cap (DistilBERT 4/4/4, DeBERTa 4/4/2). DistilBERT's dev loss mostly *falls* across epochs, so it looks **under-trained**, not over-fitted (an earlier version of this entry wrongly said it over-fits). Capacity conclusions ("DistilBERT is worse because it is smaller") are therefore confounded with training length.
- Dev families were unseen in training, but dev chose the epoch, the model and the seed; dev scores are mildly optimistic. Test-ID (in-format) and test-OOD (unseen formats) in M8 are the real estimates.

## E-006 — Local LLM baseline (`llm`: Qwen 3.5 4B via Ollama), dataset v1 / dev

- **Date:** 2026-11-28 · **Commit:** `a3abe6b` (clean) · **Report:** `reports/eval/llm_v1_dev.json` · **Command:** `uv run privymed-eval --system llm --split dev`
- **Model:** `qwen3.5:4b`, 4.2B parameters, Q4_K_M quantisation, digest `d8b0f5e9760c…`, Ollama 0.40.18, 100% on the RTX 4050 (3.4 GB). Local only (127.0.0.1); no text leaves the machine.
- **Decoding:** temperature 0, seed 0, context 8,192, thinking off, JSON-schema structured output.
- **Prompt:** instructions written from the annotation guide; 3 few-shot examples chosen deterministically from **train** (greedy entity-type cover over short documents: `adm_insurance-01548`, `rad_brief-00678`, `rad_brief-01218`); prompt SHA-256 recorded in the report.
- **Mapping:** returned strings → every whole-word, case-sensitive occurrence; unmatched strings counted as hallucinations; leading titles stripped from PATIENT/STAFF (guide rule, same as the Presidio baseline).

| Mode | Precision | Recall | F1 [95% CI] | Macro F1 |
|---|---:|---:|---|---:|
| strict | 0.957 | 0.955 | 0.956 [0.951, 0.960] | 0.963 |
| boundary | 0.961 | 0.959 | 0.960 [0.955, 0.964] | 0.966 |
| partial | 0.973 | 0.971 | 0.972 [0.968, 0.976] | 0.976 |
| overlap | 0.978 | 0.976 | 0.977 [0.973, 0.980] | 0.980 |

- **Leak rate:** 1.71%. **Latency:** 3.9 s/doc p50, 9.8 s p95 (GPU, single run) — about 170× RoBERTa.
- **Output reliability (600 docs):** 0 parse failures; 19 of 6,669 returned mentions (0.28%) not found in the note (hallucinations); 0 invalid types; 1 type conflict.
- **Per-type strict F1:** PATIENT 0.936 · STAFF 0.959 · PHONE 0.962 · ID 0.971 · ADDRESS 0.977 · HOSPITAL 0.884 (others in the report).

### Development history (disclosed)

- First full run (commit `0b266ae`, `reports/eval/superseded/llm_v1_dev_before_title_normalisation.json`): strict F1 0.868; STAFF 0.311 strict vs 0.962 partial. On 40 dev documents with STAFF mentions, Qwen kept "Dr." in 40 of 63 STAFF mentions despite the instruction not to include titles. Title stripping was then added to the mapping. This is a dev-informed change, but it only applies the annotation guide's boundary convention (identical to the Presidio baseline's normalisation); it does not change what the model detects (overlap F1 0.976 → 0.977, leak unchanged).
- The first run's mapping statistics counted 606 documents (warm-up calls included); the runner now resets detector statistics after warm-up.

### Interpretation

- A 4B instruction-tuned model with 3 examples and no fine-tuning reaches strict F1 0.956 and leaks less than tuned regex (1.71% vs 2.30%) — but leaks ~140× more than the fine-tuned RoBERTa (0.012%) and is ~170× slower.
- Its residual errors are mostly HOSPITAL and PATIENT boundaries and missed entities, not malformed output: structured output plus string mapping made the LLM pipeline reliable.
- Only one prompt and one model were evaluated (no prompt search on dev beyond the title normalisation), so this is a lower bound on what prompting can do, not a tuned result.
