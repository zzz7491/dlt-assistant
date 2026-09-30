# P3-4 Selector Edge Decomposition & Robustness Study

dataset `ba4bfb09d46aa66a` · 1930 OOS (dev 1544 / holdout 386) · definition `ea5a5d9ca181c275` · consistency pick_T0==manual True

> 唯一研究问题：CURRENT selector 早期表观优势（P2-2 S1 vs S7 Δ=0.051, Holm p=0.102 未确认）到底来自什么机制。主推断在 FINAL HOLDOUT；dev 仅用于机制发现；全 1930 仅描述性。

## STEP 4 一致性
- pick_T0（生产 selector）== manual compute_final_scores on P2-3 cache: 0/900 mismatch (PASS)
- P2-2 S1 mean 1.0878 / 选择率 C 78.89% 用 seed=None（不可复现）；P3-4 重建用可复现候选 → 选择率差异（C 4.4% vs 78.9%）本身即 seed 偶然性的证据。

## STEP 5 Candidate Set Decomposition
- candidate best/worst/mean4: 1.9715/0.2591/1.0636；variance 0.5913
- CURRENT − candidate mean = **-0.0092**（负 → selector 比随机选自家候选还差）
- CURRENT − random-choice expectation = -0.0092；regret vs oracle = 0.9171

## STEP 6/7 Selection-Conditional + Counterfactual
- 选 A: 455 (23.575%), mean-when-selected 1.1033 vs uncond 1.0648 (uplift 0.0385)
- 选 B: 416 (21.554%), mean-when-selected 1.0288 vs uncond 1.0653 (uplift -0.0364)
- 选 C: 85 (4.404%), mean-when-selected 0.9294 vs uncond 1.0731 (uplift -0.1436)
- 选 D: 974 (50.466%), mean-when-selected 1.0534 vs uncond 1.0513 (uplift 0.0021)
- C 选中期中 4 候选 mean: A=1.0118 B=0.9529 C=0.9294 D=0.9882（C 最低 → selector 在差时期追 C，而非识别 C 的优势）

## STEP 8/11 Pairwise & Correlation
- candidate hits 两两 pearson: A_B=0.116 A_C=0.0252 A_D=0.0049 B_C=-0.0442 B_D=0.0221 C_D=-0.0014
- front Jaccard 0.1122 / back 0.0637；pairwise 差异≈0（大量 tie）→ 候选近似可互换，fair-null 方差小

## STEP 9 Margin Calibration
- Spearman(margin, advantage): full -0.0066 / dev -0.0212 / holdout 0.0461 → **SELECTOR CONFIDENCE NOT CALIBRATED**

## STEP 10 Component Decomposition
- structure 分量恒 50（std=0，因生产 structure_ctx=None）；history/recent 已 P3-3 证无独立预测证据，此处仅解释为何（不）改变 ranking：OOS rank 早期冷启动主导 → 选 A/D，非有效特征

## STEP 12/13 Temporal Robustness
- quintile deltas (Q1..Q5): [0.0337, 0.035, -0.0434, -0.0512, -0.0201]
- leave-era-out full delta -0.0092; drop1=-0.0199 drop2=-0.0202 drop3=-0.0006 drop4=0.0013 drop5=-0.0065

## STEP 14/15/16/17 Nulls + Seed
- frequency-matched null: delta -0.0038 p 0.60639
- conditional strata null: delta -0.0048 p 0.61139
- C 100-seed: proxy(seed0) fixed-C mean 1.0332 (percentile 18.0); seed × era rank-stable = False (mean|rho| 0.1026) → **C SEED PERFORMANCE IS UNSTABLE**
- CURRENT mean 对任意 C seed 恒 1.0544（selector 主选 D，C 份额极低 → C seed 偶然性不影响 selector edge）

## STEP 18/19 Confirmatory H1-H4 (FINAL HOLDOUT, Holm)

| H | effect size | 95% CI | raw p | Holm p |
|---|---|---|---|---|
| H1 current>freq-null | -0.0253 | [-0.09391, 0.05572] | 0.74725 | 1.0 |
| H2 current>conditional-null | -0.0249 | — | 0.75524 | 1.0 |
| H3 margin calibrated | spearman 0.0461 | — | 0.35764 | 1.0 |
| H4 era-stable | pos_eras 2/5 | — | 1.0 | 1.0 |

## Mechanism Labels (STEP 20)

**SEED_DEPENDENT, UNCALIBRATED_SELECTOR, ERA_DEPENDENT, NOISE_COMPATIBLE**

- 解释：selector 无正向 edge（CURRENT 低于 fair-random / 候选均值）；表观优势来自：
  - **CANDIDATE_MIX_EFFECT / SELECTION_FREQUENCY_EFFECT**：候选近似可互换 + selector 对 C 的早期结构偏好
  - **SEED_DEPENDENT**：C seed 0 位于分布低位且 seed×era 排名不稳定
  - **UNCALIBRATED_SELECTOR**：margin 不校准相对优势
  - **NOISE_COMPATIBLE**：所有 confirmatory p 校正后不显著，效应量≈0

## Final Answers (STEP 25)

CURRENT FULL OOS MEAN: 1.0544
CURRENT FINAL HOLDOUT MEAN: 1.0363
FAIR RANDOM HOLDOUT MEAN: 1.0563
FREQUENCY-MATCHED NULL MEAN: 1.0583
CURRENT DELTA VS FREQUENCY NULL: -0.0038 | CI [-0.09391, 0.05572] | RAW P 0.74725 | HOLM P 1.0
CONDITIONAL NULL MEAN: 1.0592
CURRENT DELTA VS CONDITIONAL NULL: -0.0048 | HOLM P 1.0
CURRENT SELECTION SHARES: A:23.58% B:21.55% C:4.4% D:50.47%
WHEN CURRENT SELECTS C: C 0.9294 A 1.0118 B 0.9529 D 0.9882
SELECTOR MARGIN CALIBRATED: NO
EDGE TEMPORALLY STABLE: NO
EDGE SEED ROBUST: NO
PRODUCTION C SEED PERCENTILE: 18.0 (proxy seed 0, 100-seed deterministic set)
PRIMARY MECHANISM LABELS: SEED_DEPENDENT, UNCALIBRATED_SELECTOR, ERA_DEPENDENT, NOISE_COMPATIBLE
ROBUST SELECTOR EDGE: NO
EDGE COMPATIBLE WITH NOISE: YES
ML RECONSIDERATION WARRANTED: NO
PRODUCTION ALGORITHM CHANGED: NO
PRODUCTION CAP CHANGED: NO
26112 SNAPSHOT CHANGED: NO (hash bea8ef87f3f13723)
PUSH: NO
DEPLOY: NO

## Production Integrity

- production selector / weights / candidate / C seed / recent_issues=1000 / 26112 / frontend: UNCHANGED
- this gate: research only; NO PRODUCTION CHANGE

## Tests

tests/test_p34_selector_decomposition.py (run before commit)
