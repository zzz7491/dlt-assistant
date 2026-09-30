# P2-2 Selector Ablation & Statistical Validation Report

Evaluation version `p22-v1` · data 19148→26111 (1000 periods, warmup 100, evaluated 900)
S7 seeds: 50 · S0 seeds: 50 · bootstrap: 10000 resamples (seed 12345)

> **Interpretation guardrail**: this is an *exploratory model-selection* analysis with multiple variants compared against one shared sample. A variant that looks best here is a hypothesis to test out-of-sample later, NOT proof of predictive value. The ORACLE variant is post-hoc (it knows each draw's result) and is shown only as a theoretical ceiling.

## Variant Summary

| Variant | N | Total Mean | Front Mean | Back Mean | p05–p95 | Known Payout | ROI (lower bound) | Note |
|---|---|---|---|---|---|---|---|---|
| S0 RANDOM_SINGLE | 900 | 1.0445 | 0.712 | 0.3324 | 0.0–3.0 | 25385.0 | -0.7179 (exact) |  |
| S1 CURRENT_SELECTOR | 900 | 1.0878 | 0.7278 | 0.36 | 0.0–3.0 | 550.0 | -0.6944 (exact) |  |
| S2 NO_RECENT | 900 | 1.0878 | 0.7278 | 0.36 | 0.0–3.0 | 550.0 | -0.6944 (exact) |  |
| S3 NO_HISTORY | 900 | 1.0878 | 0.7278 | 0.36 | 0.0–3.0 | 550.0 | -0.6944 (exact) |  |
| S4 NO_RECENT_NO_HISTORY | 900 | 1.0878 | 0.7278 | 0.36 | 0.0–3.0 | 550.0 | -0.6944 (exact) |  |
| S5 BASE_ONLY | 900 | 1.0878 | 0.7278 | 0.36 | 0.0–3.0 | 550.0 | -0.6944 (exact) |  |
| S6 BASE_STRUCTURE | 900 | 1.0878 | 0.7278 | 0.36 | 0.0–3.0 | 550.0 | -0.6944 (exact) |  |
| S7 RANDOM_CHOICE_ABCD | 900 | 1.0368 | 0.6983 | 0.3385 | 0.0–3.0 | 22280.0 | -0.7524 (exact) |  |
| S8 ORACLE_ABCD | 900 | 1.94 | 1.2778 | 0.6622 | 1.0–3.0 | 1670.0 | -0.0722 (exact) | ⚠ ORACLE |

## Key Paired Comparisons (CURRENT S1)

| Comparison | Δmean | 95% bootstrap CI | sign-flip p (raw→Holm) | t (aux) |
|---|---|---|---|---|
| S1_vs_S2 | 0.0 | [0.0, 0.0] () | 1.0 → 1.0 | t=0.0 p=1.0 |
| S1_vs_S3 | 0.0 | [0.0, 0.0] () | 1.0 → 1.0 | t=0.0 p=1.0 |
| S1_vs_S4 | 0.0 | [0.0, 0.0] () | 1.0 → 1.0 | t=0.0 p=1.0 |
| S1_vs_S7 | 0.05098 | [0.00015, 0.10133] (excludes 0) | 0.02549 → 0.10196 | t=1.996 p=0.04593 |

## Selection Frequency (S1 CURRENT)

A 17.67% · B 0.44% · C 78.89% · D 3.0%

Early {'A': 33.67, 'B': 1.33, 'C': 56.0, 'D': 9.0} · Middle {'A': 8.67, 'B': 0.0, 'C': 91.33, 'D': 0.0} · Late {'A': 10.67, 'B': 0.0, 'C': 89.33, 'D': 0.0}

## Switching / Chasing (S1)

- switch rate: 0.1635 (mean run length 6.027)
- switch-after-win rate: 0.1765 (595 win events)
- switch-after-loss rate: 0.1382 (304 loss events)

## Temporal Stability

### S1 (CURRENT) total-hit mean by third

| segment | mean | p05 | p95 |
|---|---|---|---|
| early | 1.13 | 0.0 | 3.0 |
| middle | 1.17 | 0.0 | 3.0 |
| late | 0.9633 | 0.0 | 2.0 |

### Rolling S1 − S2 delta per 100-period block

| block | mean Δ (S1−S2) | n |
|---|---|---|
| 0 | 0.0 | 100 |
| 1 | 0.0 | 100 |
| 2 | 0.0 | 100 |
| 3 | 0.0 | 100 |
| 4 | 0.0 | 100 |
| 5 | 0.0 | 100 |
| 6 | 0.0 | 100 |
| 7 | 0.0 | 100 |
| 8 | 0.0 | 100 |

## Fair Null Baseline (S7 RANDOM-CHOICE-ABCD)

- per-seed mean distribution (across 50 seeds): mean 1.0368, p05 0.9969, p95 1.0662, p99 1.0768
- full pooled: mean 1.0368 (n 45000)
- **S1 vs S7**: Δ = 0.05098 (95% CI [0.00015, 0.10133], CI excludes 0)

## Oracle Upper Bound (S8, POST-HOC)

- ORACLE mean total hit 1.94 (p05–p95 1.0–3.0). Ceiling of choosing best-of-4 after seeing each result. **INVALID FOR PRODUCTION.**
- Independent random single ticket (S0): mean 1.0445.

## Interpretation

Objective read (no purchase/prediction recommendation):
- Compare S1 (current selector) against S7 (random choice among the same four candidates) to isolate the *selection* mechanism from candidate quality.
- A/B/C/D all sit near the independent-random-ticket expectation, so the selector's apparent edge over a single random ticket is largely explained by random-choice among candidates.
- NO_RECENT / NO_HISTORY ablations test whether the recent-5 or history feedback terms actually move out-of-sample performance.
- If the S1 vs S2 (drop recent) paired CI contains 0, the recent-feedback term is not supported by this sample; likewise for S3 (drop history).
- Any apparent advantage that only appears in one of EARLY/MIDDLE/LATE is UNSTABLE.
