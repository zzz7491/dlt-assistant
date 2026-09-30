# P2-3 Simplified Selector Candidate Report

Evaluation `p23-v1` · dev 630 / holdout 270 draws · definition hash `2878c6851a8b33d8` (frozen 2026-09-30T18:51:15) · cache persisted-reuse

> **Guardrail**: exploratory model-selection. The HOLDOUT third (last 30%) is the decision basis; no formula was tuned to holdout. A 'winner' here is a hypothesis for P2-4, not a claim of predictive value. C is a random baseline, not an 'optimal model'.

## Candidate Results (mean total hits)

### DEV

| Candidate | Total Mean | Front | Back | >=3 Front | 2 Back | Prize Hits | Known Payout | ROI (lb) |
|---|---|---|---|---|---|---|---|---|
| T0 CURRENT_SELECTOR | 0.9984 | 0.7016 | 0.2968 | 5 | 6 | 36 | 210.0 | -0.8333 |
| T1 FIXED_A | 1.0714 | 0.7349 | 0.3365 | 8 | 10 | 45 | 255.0 | -0.7976 |
| T2 FIXED_B | 1.0429 | 0.7079 | 0.3349 | 11 | 12 | 43 | 490.0 | -0.6111 |
| T3 FIXED_C | 1.0159 | 0.681 | 0.3349 | 6 | 8 | 40 | 230.0 | -0.8175 |
| T4 FIXED_D | 1.0063 | 0.6905 | 0.3159 | 8 | 9 | 44 | 425.0 | -0.6627 |
| T5 SIMPLE_BASE | 0.9984 | 0.7016 | 0.2968 | 5 | 6 | 36 | 210.0 | -0.8333 |
| T6 SIMPLE_STRUCTURE | 1.0127 | 0.7 | 0.3127 | 10 | 9 | 43 | 420.0 | -0.6667 |
| T7 SIMPLE_BASE_STRUCTURE | 1.0 | 0.7048 | 0.2952 | 5 | 6 | 35 | 215.0 | -0.8294 |
| T8 DIVERSITY_SELECTOR | 1.0873 | 0.7365 | 0.3508 | 5 | 10 | 49 | 265.0 | -0.7897 |
| S7 RANDOM-CHOICE | 1.03415873015873 | (pooled n=31500 across 50 seeds) | | | | | | |

### HOLDOUT

| Candidate | Total Mean | Front | Back | >=3 Front | 2 Back | Prize Hits | Known Payout | ROI (lb) |
|---|---|---|---|---|---|---|---|---|
| T0 CURRENT_SELECTOR | 1.0148 | 0.6741 | 0.3407 | 2 | 7 | 16 | 110.0 | -0.7963 |
| T1 FIXED_A | 1.0185 | 0.6778 | 0.3407 | 2 | 7 | 16 | 110.0 | -0.7963 |
| T2 FIXED_B | 1.063 | 0.7407 | 0.3222 | 5 | 2 | 18 | 100.0 | -0.8148 |
| T3 FIXED_C | 1.0407 | 0.6704 | 0.3704 | 4 | 8 | 22 | 120.0 | -0.7778 |
| T4 FIXED_D | 0.9704 | 0.6296 | 0.3407 | 1 | 2 | 13 | 65.0 | -0.8796 |
| T5 SIMPLE_BASE | 1.0148 | 0.6741 | 0.3407 | 2 | 7 | 16 | 110.0 | -0.7963 |
| T6 SIMPLE_STRUCTURE | 0.9593 | 0.6259 | 0.3333 | 1 | 2 | 13 | 65.0 | -0.8796 |
| T7 SIMPLE_BASE_STRUCTURE | 1.0148 | 0.6741 | 0.3407 | 2 | 7 | 16 | 110.0 | -0.7963 |
| T8 DIVERSITY_SELECTOR | 1.0037 | 0.6667 | 0.337 | 3 | 4 | 14 | 70.0 | -0.8704 |
| S7 RANDOM-CHOICE | 1.0282222222222221 | (pooled n=13500 across 50 seeds) | | | | | | |

## Production C Seed Sensitivity

- 50-seed C distribution mean 1.0576, p05 1.0224, p95 1.1006
- fixed proxy seed 0 mean 1.0133 = **percentile 4.0** within the 50-seed distribution
- production C uses seed=null (non-reproducible); seed 0 is a deterministic proxy

## Holdout Paired Comparisons (vs CURRENT & vs S7, Holm-adjusted)

| candidate | vs T0 Δ | vs T0 95% CI | vs T0 p_adj | vs S7 Δ | vs S7 95% CI | vs S7 p_adj |
|---|---|---|---|---|---|---|
| T1 FIXED_A | 0.0037 | [0.0, 0.01111] | 1.0 | -0.0097 | [-0.09897, 0.07993] | 1.0 |
| T2 FIXED_B | 0.04815 | [-0.08889, 0.18519] | 1.0 | 0.03474 | [-0.05141, 0.12037] | 1.0 |
| T3 FIXED_C | 0.02593 | [-0.12593, 0.18148] | 1.0 | 0.01252 | [-0.08119, 0.11] | 1.0 |
| T4 FIXED_D | -0.04444 | [-0.19259, 0.1] | 1.0 | -0.05785 | [-0.14615, 0.03089] | 0.72765 |
| T5 SIMPLE_BASE | 0.0 | [0.0, 0.0] | 1.0 | -0.01341 | [-0.1023, 0.07585] | 1.0 |
| T6 SIMPLE_STRUCTURE | -0.05556 | [-0.2, 0.08889] | 1.0 | -0.06896 | [-0.1583, 0.02163] | 0.59568 |
| T7 SIMPLE_BASE_STRUCTURE | 0.0 | [0.0, 0.0] | 1.0 | -0.01341 | [-0.1023, 0.07585] | 1.0 |
| T8 DIVERSITY_SELECTOR | -0.01111 | [-0.15185, 0.12963] | 1.0 | -0.02452 | [-0.1183, 0.07044] | 1.0 |

## Temporal Stability (T0 & T5 & T7 & T8)

- T0 holdout early/mid/late mean: 1.0222 / 0.9444 / 1.0778
- T5 holdout early/mid/late mean: 1.0222 / 0.9444 / 1.0778
- T7 holdout early/mid/late mean: 1.0222 / 0.9444 / 1.0778
- T8 holdout early/mid/late mean: 1.0556 / 1.0111 / 0.9444

## Complexity Comparison

| variant | signals | # | recent | history | structure | learned-wt | stateful | explainability |
|---|---|---|---|---|---|---|---|---|
| T0 | base,history,recent,structure,risk | 5 | True | True | True | False | True | medium (5-factor weighted sum + OOS rank/history) |
| T1 | none | 1 | False | False | False | False | False | trivial (always strategy A) |
| T2 | none | 1 | False | False | False | False | False | trivial (always strategy B) |
| T3 | none | 1 | False | False | False | False | False | trivial (always strategy C = random) |
| T4 | none | 1 | False | False | False | False | False | trivial (always strategy D = scored) |
| T5 | base,risk | 2 | False | False | False | False | True | high (rank-based base + structural risk penalty only) |
| T6 | structure | 1 | False | False | True | False | False | high (single pre-target structure quality score) |
| T7 | base,structure | 2 | False | False | True | False | False | high (pre-fixed 50/50 base+structure, no tuning) |
| T8 | candidate_diversity | 1 | False | False | False | False | False | high (max symmetric-diff distance from other 3 candidates) |

## Decision

**KEEP_CURRENT_TEMPORARILY**

- best simple candidate = T2 (holdout mean 1.063)
- not worse than CURRENT on holdout: True
- beats fair null (S7): False
- best simple candidate T2 holdout mean 1.0630 vs CURRENT 1.0148; vs fair-null S7 adj p=1.0000; vs CURRENT adj p=1.0000. Keep current temporarily (no strong evidence a simple candidate is better)
