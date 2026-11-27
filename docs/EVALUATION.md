# Evaluation protocol

All systems (regex, Presidio, transformer, LLM, hybrid) are scored by one evaluator, `privymed.evaluation`, on character-offset spans (ADR-001). This document defines exactly what the numbers mean.

## Matching modes

| Mode | A prediction is a true positive when it… | Question answered |
|---|---|---|
| `strict` | has exactly the gold boundaries **and** label | Is it exactly right? (headline metric) |
| `boundary` | has exactly the gold boundaries (any label) | Did it find the right text? |
| `partial` | overlaps the gold span and has its label | Is it roughly right? |
| `overlap` | overlaps the gold span (any label) | Would redaction have hidden it? (privacy view) |

## Rules common to all modes

- **One-to-one matching, maximum cardinality.** A prediction matches at most one gold span and vice versa. The matching maximises the number of matched pairs, then total character overlap (Hungarian algorithm via `scipy.optimize.linear_sum_assignment`; deterministic). An earlier greedy largest-overlap-first rule was not optimal when predictions overlap several gold spans (review M3-4: gold `[0,10)` `[10,20)`, predictions `[2,18)` `[0,3)` → greedy 1 TP, optimal 2 TP). It produced identical counts for the regex and Presidio baselines, whose outputs never overlap.
- **Duplicates.** Predictions with the same `(start, end, label)` are collapsed before matching.
- **Attribution.** True positives and false negatives are counted under the gold label; false positives under the predicted label. (So in `boundary` mode a wrong-label prediction is credited to the gold type.)
- **Missing documents** count as "no predictions". Predictions for unknown `doc_id`s are an error.
- **Micro** scores pool counts over all labels. **Macro** F1 averages per-label F1 over labels present in gold. Consequence: false positives of a label that never occurs in gold lower micro precision but not macro F1.
- **Same range, two labels.** Deduplication is by `(start, end, label)`, so a system that emits PATIENT and STAFF on the same range gets at most one TP and at least one FP, even in label-agnostic modes. Systems should emit one label per range.

## Leak rate

The share of gold PII **characters** not covered by any prediction, ignoring labels and boundaries. This is the most direct privacy metric: 0% means every character of every gold entity would have been redacted.

## Confidence intervals

95% percentile bootstrap over **documents** (1,000 resamples, fixed seed). Resampling documents rather than spans respects the fact that spans within one document are correlated.

## Latency

Per-document wall-clock time of `Detector.detect`, single process, after a warm-up on the first five documents; model loading is reported separately as `first_call_ms`. Each report is a **single run**: repeated runs varied by up to ~35% (review M3-7: Presidio p50 20.9 vs 28.0 ms), so latency is reported as an order of magnitude until Milestone 8, which will use repeated runs, a fixed thread count, batched inference for batch-capable systems, and record the device.

## Verification of the evaluator itself

- Hand-computed counts for one document exercising every mode (`tests/test_metrics.py`).
- Maximum-cardinality matching checked against a brute-force optimum on 1,200 random cases with overlapping predictions, plus the review counterexample.
- Edge cases: one prediction covering two gold spans, two predictions on one gold span, entity-free documents, missing documents, macro with absent labels.
- **Cross-check:** strict micro precision/recall/F1 equal `seqeval` (IOB2, strict mode) on 435 generated documents with realistic perturbations (misses, relabels, shrunk spans, spurious predictions).

## Data usage

- Development and tuning: `train` and `dev` only.
- `test_id` and `test_ood`: evaluated once at Milestone 8 by the final-evaluation script, after `verify_manifest()` passes (CLAUDE.md rule 3).
