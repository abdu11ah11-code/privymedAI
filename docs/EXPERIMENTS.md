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

- **Date:** 2026-11-27 · **Grid:** `bash scripts/run_m4_grid.sh` (3 models × seeds 13, 42, 7) · **Run records:** `reports/train/<model>_s<seed>.json`
- **Commits:** DistilBERT and RoBERTa runs at `c8ed4b8`; DeBERTa runs at `2982ec7` (after the fp32-weights fix below). All records `git.dirty = false`. Between the two commits only progress logging and explicit fp32 loading changed; DistilBERT and RoBERTa already load as fp32 by default, so the runs are comparable.
- **Hardware:** RTX 4050 Laptop 6 GB, bf16 autocast, fp32 master weights. **Training data:** train (4,000 docs, 4,034 windows at max length 512 / stride 64). **Selection:** best epoch by dev strict micro F1 (≤ 4 epochs, patience 2).
- **Hyperparameters:** each model's commonly recommended learning rate (DistilBERT 5e-5, RoBERTa and DeBERTa 3e-5), effective batch 16, warmup 10%, weight decay 0.01. Not tuned per model — a fair-but-limited comparison.

| Model | Params | Dev strict F1 (mean ± std, 3 seeds) | Dev overlap F1 | Dev leak | Best epochs | Train time / run | Peak VRAM |
|---|---:|---|---:|---:|---|---:|---:|
| distilbert-base-cased | 66M | 0.9115 ± 0.0105 | 0.9627 ± 0.0011 | 0.48% | 4, 4, 4 | 3.7 min | 2.48 GiB |
| roberta-base | 125M | **0.9912 ± 0.0010** | 0.9951 ± 0.0020 | 0.02% | 3, 2, 4 | 6.9 min | 3.74 GiB |
| microsoft/deberta-v3-base | 184M | 0.9930 ± 0.0069 | 0.9955 ± 0.0049 | 0.02% | 4, 4, 2 | 22.7 min | 5.37 GiB |

Per seed (13 / 42 / 7): DistilBERT 0.9056 / 0.9053 / 0.9237 · RoBERTa 0.9914 / 0.9901 / 0.9920 · DeBERTa 0.9855 / 0.9945 / 0.9991.

### Model selection

**RoBERTa-base**, representative checkpoint **`roberta_s13`** (median seed, not best seed — choosing the best seed would be one more act of tuning on dev).

- DeBERTa's mean is 0.0018 higher, which is smaller than its own seed standard deviation (0.0069): no meaningful difference.
- RoBERTa is ~7× more stable across seeds, ~3.3× faster to train, uses 1.6 GiB less memory and is ~32% smaller (relevant for ONNX and deployment in M9–M11).
- DistilBERT is kept as the small-model candidate for the optimisation milestone.

### Selected model on dev (`privymed-eval --system transformer --param checkpoint=models/roberta_s13`)

Report: `reports/eval/transformer_v1_dev_roberta_s13.json`

| Mode | Precision | Recall | F1 [95% CI] |
|---|---:|---:|---|
| strict | 0.986 | 0.997 | 0.991 [0.990, 0.993] |
| boundary | 0.989 | 1.000 | 0.994 [0.993, 0.996] |
| overlap | 0.990 | 1.000 | 0.995 [0.994, 0.996] |

Leak rate **0.010%** (commit `269c68c`, clean; strict F1 0.9914 = training record). Per-type strict F1: PATIENT 0.982 · STAFF 0.985 · DATE 0.999 · PHONE 1.000 · EMAIL 1.000 · CNIC 1.000 · ID 0.998 · ADDRESS 0.997 · HOSPITAL 0.979. Latency ~15 ms/doc mean (GPU, whole-split batched; single run).

### Reproducibility checks

- A reloaded checkpoint reproduces its training-time dev strict F1 **exactly** (roberta_s13 0.9914, deberta_s42 0.9945, distilbert_s7 0.9237) when inference uses the same call shape as training (one call over the split). Chunking documents differently changes how windows are batched and moved scores by ±0.0002 under bf16.
- Same-seed training is **not** bitwise reproducible on this GPU (deterministic algorithms are off): a preliminary DistilBERT seed-13 run gave 0.8994, the grid run 0.9056. Seed-to-seed std is therefore the honest uncertainty measure.

### Problems found and fixed during the grid

- **DeBERTa NaN loss:** Transformers 5 keeps a checkpoint's stored dtype; `deberta-v3-base` is stored in fp16, so training ran with fp16 master weights → NaN from the first steps (record deleted). Weights are now always loaded as fp32; a non-finite loss aborts the run.
- **DeBERTa stall:** batch 8 filled the 6 GB GPU and Windows spilled into system RAM (no epoch in 46 min). Batch 4 × accumulation 4 keeps the effective batch at 16.
- **DeBERTa tokenizer offsets** include SentencePiece's leading space (39,572 straddling tokens before `clean_offsets`; 0 after).
- **RoBERTa BPE** merges "(+" / "(#": 323 unavoidable boundary straddles on train (0 on dev).

### Interpretation and caveats

- On dev, the fine-tuned model leaks ~230× less PII than tuned regex (0.010% vs 2.30%) and ~1,300× less than Presidio, with no hand-written rules; its largest gains are on context-dependent types (STAFF 0.985 vs regex 0.940, HOSPITAL 0.980 vs 0.929).
- Dev families were unseen in training, but dev chose the best epoch and the model; dev scores are therefore mildly optimistic. Test-ID (in-format) and test-OOD (unseen formats) in M8 are the real estimates.
- The DistilBERT gap (0.91) shows capacity matters on unseen document structures: DistilBERT overfits train families (train loss → 0.006 while dev loss rises after epoch 2).
