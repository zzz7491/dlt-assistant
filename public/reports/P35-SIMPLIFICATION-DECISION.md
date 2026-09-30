# P3-5 Production Simplification Decision (Research Closure)

dataset `ba4bfb09d46aa66a` · 1930 OOS (dev 1544 / holdout 386) · NO PRODUCTION CHANGE · source: P3-2 cache + P3-4 reconstruction

> 唯一目标：基于 P2+P3 全部 OOS/holdout 证据，判断当前生产推荐链的复杂度哪些有证据支持、哪些仅娱乐/解释、哪些可简化、哪些当前绝不应改。本 Gate 只形成决策建议与冻结基线。

## Baseline B0-B7 (mean total hits, full OOS / holdout)

| baseline | full | holdout | variance |
|---|---|---|---|
| B0_uniform_random_valid_ticket | 1.0508 | 1.0337 | 0.7871 |
| B1_fixed_A | 1.0648 | 1.0596 | 0.8088 |
| B2_fixed_B | 1.0653 | 1.0544 | 0.8071 |
| B3_fixed_C | 1.0731 | 1.1321 | 0.7921 |
| B4_fixed_D | 1.0513 | 0.9793 | 0.8114 |
| B5_random_choice_ABCD | 1.0636 | 1.0563 | 0.2136 |
| B6_frequency_matched_random_selector | 1.0636 | 1.0563 | 0.2136 |
| B7_CURRENT | 1.0544 | 1.0363 | 0.8007 |

## Complexity Cost (objective metrics)

| baseline | historical state | scoring comps | RNG | walk-forward | cand gens |
|---|---|---|---|---|---|
| B0_uniform_random_valid_ticket | none | 0 | yes (ticket) | no | 0 |
| B1_fixed_A | last 1000 issues | freq+recent+hot/cold+balance | yes (strategy A sample) | no | 1 |
| B2_fixed_B | last 1000 issues | freq+recent+hot/cold | yes (strategy B sample) | no | 1 |
| B3_fixed_C | none | 0 | yes (random 5+2) | no | 1 |
| B4_fixed_D | last 1000 issues | heat+missing+trend+inherit + combo 5 factors | no (deterministic top-1) | no | 1 |
| B5_random_choice_ABCD | last 1000 issues | 4 candidate generators | yes (choice) | no | 4 |
| B6_frequency_matched_random_selector | last 1000 issues + OOS selection history | 4 candidate generators | yes (choice) | yes (selection frequency) | 4 |
| B7_CURRENT | last 1000 issues + walk-forward OOS history/recent/rank | base+history+recent+structure+risk + 4 candidate generators | yes (A/B/C sample) + C seed=null risk | yes (OOS maps, stateful) | 4 |

## Simplification Counterfactual (STEP 8)

- CURRENT vs random-choice(ABCD): full Δ=-0.0092 CI[-0.0431,0.0246] (contains 0); holdout Δ=-0.0201 CI[-0.0939,0.0544] (contains 0)
- CURRENT vs fixed-D (deterministic): holdout Δ=0.057 CI[-0.0648,0.1813]
- claim_allowed (complex selector actually better): False → **NO — simpler alternative not beaten****

## RNG / Reproducibility (STEP 9)

- C RNG reproducibility risk: **True** (production recommend() uses recommend.seed=null → C strategy RNG state differs every run; P2-3 seed-0 proxy sits at 4th percentile of 50-seed C distribution; P3-4 C seed x era rank unstable (mean|rho|=0.10).)
- future fix options: deterministic seed (config recommend.seed fixed); snapshot-bound seed (seed derived from issue/dataset sha); remove RNG dependency for C (deterministic pseudo-random or fixed strategy) · this Gate: NO (no production modification in P3-5)

## 1000-draw Cap (STEP 10)

- data retention: KEEP (1000 draws retained; not the question here)
- analysis window decision: **KEEP_1000_TEMPORARILY**
- evidence: P3-2 FULL vs 1000: A delta -0.067 (Holm p=0.159), D -0.025 (Holm p=0.614); no window confirmed better; B NO_WINDOW_EDGE

## Production Options (STEP 13)

### OPTION_A_KEEP_CURRENT
  - implementation_impact: none
  - reproducibility: LOW (C seed=None, stateful walk-forward selector)
  - research_evidence: no confirmed edge; keeps complexity without demonstrated benefit
  - backward_compatibility: full
  - snapshot_compatibility: full (26112 unchanged)
  - migration_risk: none

### OPTION_B_SIMPLIFY_SELECTOR
  - implementation_impact: replace 5-factor + OOS walk-forward selector with fixed or random-choice among A/B/C/D; remove stateful OOS maps
  - reproducibility: MEDIUM-HIGH (deterministic or fixed seed)
  - research_evidence: P3-4: simplification loses nothing confirmed (all nulls not beaten; candidate means ~= random)
  - backward_compatibility: candidate generation unchanged; only selection policy changes
  - snapshot_compatibility: requires new snapshot (numbers may shift) - re-publish
  - migration_risk: LOW (selection layer isolated; requires a production-change Gate)

### OPTION_C_BASELINE_FIRST_DETERMINISTIC
  - implementation_impact: publish a single deterministic entertainment ticket (e.g. fixed C with deterministic seed) - remove A/B/D + selector
  - reproducibility: HIGH (deterministic, seed-bound)
  - research_evidence: P3-3/P3-4: no predictive feature/edge; simplest honest baseline
  - backward_compatibility: BREAKING (removes multi-candidate display)
  - snapshot_compatibility: new snapshot required; 26112 immutable until then
  - migration_risk: MEDIUM (largest change; separate production-change Gate)

## P35 Recommended Production Direction (STEP 14)

**KEEP_CURRENT_TEMPORARILY** (simplification warranted for engineering: True) — NOT a deployment authorization.

no confirmatory evidence supports either keeping the complex selector for a predicted benefit OR changing it now. Selector edge is noise-compatible (P3-4); no predictive feature confirmed (P3-3). A production change (OPTION B/C) would be engineering-simplification-driven, not evidence-confirmed; it requires a separate, explicitly authorized production-change Gate.

## Component Evidence Classification (STEP 4)

| component | role | classification |
|---|---|---|
| A | PRODUCTION_USED | OPERATIONALLY_REQUIRED / ENTERTAINMENT_ANALYTIC |
| B | PRODUCTION_USED | OPERATIONALLY_REQUIRED / ENTERTAINMENT_ANALYTIC |
| C | PRODUCTION_USED | ENTERTAINMENT_ANALYTIC / LEGACY_COMPATIBILITY |
| D | PRODUCTION_USED | OPERATIONALLY_REQUIRED / PREDICTIVE_INCONCLUSIVE |
| frequency | PRODUCTION_USED | PREDICTIVE_UNSUPPORTED / ENTERTAINMENT_ANALYTIC / REDUNDANT |
| omission | PRODUCTION_USED | PREDICTIVE_UNSUPPORTED / ENTERTAINMENT_ANALYTIC |
| hot_cold | PRODUCTION_USED | PREDICTIVE_UNSUPPORTED / ENTERTAINMENT_ANALYTIC / REDUNDANT |
| trend | PRODUCTION_USED | PREDICTIVE_UNSUPPORTED / ENTERTAINMENT_ANALYTIC |
| inherit | PRODUCTION_USED | PREDICTIVE_INCONCLUSIVE / ENTERTAINMENT_ANALYTIC |
| odd_even_big_small_zone_sum_span | PRODUCTION_USED | PREDICTIVE_UNSUPPORTED / ENTERTAINMENT_ANALYTIC |
| base | PRODUCTION_USED | OPERATIONALLY_REQUIRED |
| risk | PRODUCTION_USED | OPERATIONALLY_REQUIRED / ENTERTAINMENT_ANALYTIC |
| history | PRODUCTION_USED | PREDICTIVE_INCONCLUSIVE / OPERATIONALLY_REQUIRED |
| recent | PRODUCTION_USED | PREDICTIVE_INCONCLUSIVE / OPERATIONALLY_REQUIRED |
| structure | PRODUCTION_USED | PREDICTIVE_UNSUPPORTED / ENTERTAINMENT_ANALYTIC |
| final_score | PRODUCTION_USED | OPERATIONALLY_REQUIRED / PREDICTIVE_INCONCLUSIVE |
| selector | PRODUCTION_USED | PREDICTIVE_UNSUPPORTED / OPERATIONALLY_REQUIRED |
| c_rng_seed | PRODUCTION_USED | LEGACY_COMPATIBILITY |
| recent_issues_1000 | OPERATIONALLY_REQUIRED | OPERATIONALLY_REQUIRED / LEGACY_COMPATIBILITY |
| publication_snapshot | PUBLICATION_CRITICAL | PUBLICATION_REQUIRED / OPERATIONALLY_REQUIRED |
| explanation_generation | DISPLAY_ONLY | ENTERTAINMENT_ANALYTIC |
| frontend_trend | DISPLAY_ONLY | ENTERTAINMENT_ANALYTIC |

## Product Semantics & Explanation Audit (STEP 11/12)

- FROZEN wording: DLT results are random; historical statistics are for entertainment analysis / trend display / explaining recommendation generation ONLY.
- BANNED wording (never claim): 提高中奖概率 / 预测下一期 / AI预测 / 高概率号码 / 稳赢 / 命中模型.
- Frontend findings: public/experiment.html: ['中奖概率']; public/pick.html: ['中奖概率']  → flagged for FUTURE revision (this Gate: NO UI change)
- Explanation engine (src/explanation.py): **PASS (no unsupported→predictive packaging)** (disclaimer present = True)

## Research Stop Rule (STEP 15)

- STOP feature mining: **True**
- STOP selector tuning: **True**
- STOP ML escalation: **True**

Future research requires: a NEW testable hypothesis INDEPENDENT of the current historical-statistics system; pre-registered hypothesis + mechanism + metric + holdout protocol BEFORE running; immutable dataset version + walk-forward + baseline + effect size + CI + multiple-comparison correction + seed policy + negative-result retention; no post-hoc production change

## FINAL ANSWERS (STEP 20)

P2/P3 PREDICTIVE EVIDENCE: NOT CONFIRMED
IDENTIFIABLE PREDICTIVE FEATURE: NO
ROBUST SELECTOR EDGE: NO
ML JUSTIFIED: NO
CURRENT COMPLEXITY PREDICTIVELY JUSTIFIED: NO
CURRENT PIPELINE OPERATIONALLY VALID: YES (entertainment/explanation, not prediction)
C RNG REPRODUCIBILITY RISK: YES
FULL HISTORY SUPERIOR TO 1000: NO
1000 WINDOW DECISION: KEEP_1000_TEMPORARILY
FEATURE MINING SHOULD CONTINUE: NO
SELECTOR TUNING SHOULD CONTINUE: NO
PRODUCTION DIRECTION: KEEP_CURRENT_TEMPORARILY
PRODUCTION CHANGE AUTHORIZED: NO
PRODUCTION ALGORITHM CHANGED: NO
PRODUCTION CAP CHANGED: NO
26112 SNAPSHOT CHANGED: NO
PUSH: NO
DEPLOY: NO
