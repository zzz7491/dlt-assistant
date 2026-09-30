# P3-3 Feature Validity & Ablation Study

dataset `ba4bfb09d46aa66a` · OOS 1930 (dev 1544 / holdout 386) · ablation source cache · production unchanged True

> Two levels: LEVEL 1 single-number (does a number's freq/omit/temperature/overlap relate to next-draw appearance), LEVEL 2 candidate (does sum/span/odd-even/size/structure score relate to final hit count). All features computed from issues[:t] only (leakage contract). Metrics are descriptive; AUC≈0.5 = no discrimination.

## Feature Inventory & Provenance (from real production code)

| feature | zone | lookback | provenance | consumer |
|---|---|---|---|---|
| frequency (freq_ratio) | front+back | FULL evidence | RAW_HISTORY_DERIVED | analyzer.analyze -> A/B front_freq + scorer heat(recent_100) |
| recent frequency (recent_ratio) | front+back | recent_window=50 | RAW_HISTORY_DERIVED | analyzer.front_recent_freq -> A/B _weighted |
| omission (current) (cur_omit) | front+back | to last hit | RAW_HISTORY_DERIVED | analyzer.front_cur_omit -> B cold + scorer missing |
| omission (avg cycle) (avg_omit) | front+back | FULL | RAW_HISTORY_DERIVED | analyzer.analyze_missing_cycle |
| omission (max) (max_omit) | front+back | FULL | RAW_HISTORY_DERIVED | analyzer.front_max_omit |
| omission ratio (omit_ratio) | front+back | FULL | RAW_HISTORY_DERIVED | derived |
| temperature/trend (trend) | front+back | 30 vs 100 | RAW_HISTORY_DERIVED | analyzer.analyze_number_temperature -> D |
| hot indicator (hot) | front+back | FULL | RAW_HISTORY_DERIVED | analyzer.front_hot |
| previous-draw overlap indicator (in_prev) | front+back | 1 | RAW_HISTORY_DERIVED | analyzer + scorer inherit |
| size zone (zone) | front(5)/back(2) | static | STATIC_RULE | analyzer zone_dist |

**final_score components provenance:** base=STATIC_RULE; history=OUTCOME_FEEDBACK; recent=OUTCOME_FEEDBACK; structure=CANDIDATE_DERIVED; risk=STATIC_RULE

## LEVEL 1 Single-Number Features (front, pooled OOS, n=67550)

| feature | ROC-AUC | Spearman | top-dec | bot-dec | base | beats_null | decision |
|---|---|---|---|---|---|---|---|
| freq_ratio | 0.4971 | -0.0036 | 0.1426 | 0.151 | 0.1429 | False | REDUNDANT |
| recent_ratio | 0.5025 | 0.003 | 0.1469 | 0.1427 | 0.1429 | False | UNSUPPORTED |
| cur_omit | 0.4947 | -0.0064 | 0.142 | 0.1476 | 0.1429 | False | REDUNDANT |
| max_omit | 0.4938 | -0.0076 | 0.138 | 0.1506 | 0.1429 | False | INCONCLUSIVE |
| avg_omit | 0.5026 | 0.0031 | 0.1452 | 0.1418 | 0.1429 | False | REDUNDANT |
| omit_ratio | 0.4945 | -0.0067 | 0.1397 | 0.1476 | 0.1429 | False | REDUNDANT |
| trend | 0.4948 | -0.0063 | 0.1395 | 0.1483 | 0.1429 | False | INCONCLUSIVE |
| hot | 0.4984 | -0.0025 | 0.1363 | 0.1421 | 0.1429 | False | REDUNDANT |
| in_prev | 0.5017 | 0.0033 | 0.1461 | 0.1418 | 0.1429 | False | INCONCLUSIVE |
| zone | 0.4914 | -0.0106 | 0.1356 | 0.1547 | 0.1429 | False | INCONCLUSIVE |

## Back-zone single features

| feature | ROC-AUC | Spearman | base | decision |
|---|---|---|---|---|
| freq_ratio | 0.5001 | 0.0001 | 0.1667 | REDUNDANT |
| recent_ratio | 0.5075 | 0.0098 | 0.1667 | UNSUPPORTED |
| cur_omit | 0.5057 | 0.0074 | 0.1667 | REDUNDANT |
| max_omit | 0.4943 | -0.0074 | 0.1667 | UNSUPPORTED |
| avg_omit | 0.498 | -0.0025 | 0.1667 | REDUNDANT |
| omit_ratio | 0.5059 | 0.0076 | 0.1667 | REDUNDANT |
| trend | 0.502 | 0.0025 | 0.1667 | UNSUPPORTED |
| hot | 0.5021 | 0.0041 | 0.1667 | UNSUPPORTED |
| in_prev | 0.501 | 0.0021 | 0.1667 | UNSUPPORTED |
| zone | 0.504 | 0.006 | 0.1667 | INCONCLUSIVE |

## LEVEL 2 Candidate Features (D-1000 reuse, total-hits label)

| feature | Spearman | top-dec | bot-dec | decision |
|---|---|---|---|---|
| back_overlap_prev | 0.0 | 0.9948 | 1.0518 | INCONCLUSIVE |
| back_span | 0.0267 | 1.057 | 1.0518 | INCONCLUSIVE |
| big_cnt | -0.0178 | 0.9637 | 1.1451 | INCONCLUSIVE |
| big_small_match | 0.0 | 0.9948 | 1.0518 | INCONCLUSIVE |
| combo_score | -0.0072 | 1.0674 | 1.1813 | INCONCLUSIVE |
| front_overlap_prev | -0.0278 | 0.9585 | 1.0518 | INCONCLUSIVE |
| front_span | 0.0305 | 1.1554 | 1.0881 | INCONCLUSIVE |
| front_sum | 0.011 | 1.0674 | 1.0052 | INCONCLUSIVE |
| inherit_match | -0.021 | 1.1503 | 1.0829 | INCONCLUSIVE |
| odd_cnt | -0.0157 | 0.9948 | 1.1036 | INCONCLUSIVE |
| odd_even_match | 0.0077 | 1.0 | 1.0 | INCONCLUSIVE |
| sum_in_p25_75 | -0.0199 | 0.9948 | 1.0622 | INCONCLUSIVE |
| sum_span_match | -0.0199 | 0.9948 | 1.0622 | INCONCLUSIVE |
| zone_match | 0.0013 | 1.0466 | 1.114 | INCONCLUSIVE |

## Null Controls (50 deterministic seeds)

- front random-score AUC p05/p50/p95 = 0.4948/0.4999/0.5047
- front shuffled-null: freq_ratio=0.4971 (null_p95 0.5049, beats=False), recent_ratio=0.5025 (null_p95 0.5054, beats=False), cur_omit=0.4947 (null_p95 0.5043, beats=False)

## Redundancy (|Spearman| >= 0.7 → REDUNDANT GROUPS)

- cur_omit ~ omit_ratio  (|rho|=0.996)
- freq_ratio ~ avg_omit  (|rho|=0.893)

## D Feature Ablation (FULL_D control, 1930 OOS targets, paired)

| variant | FULL mean | variant mean | delta | CI95 | Holm p | FDR q | decision |
|---|---|---|---|---|---|---|---|
| NO_HEAT | 1.0513 | 1.0207 | 0.03057 | [-0.00518,0.06684] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_MISSING | 1.0513 | 1.0725 | -0.02124 | [-0.08083,0.03782] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_TREND | 1.0513 | 1.0482 | 0.00311 | [-0.02332,0.02953] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_INHERIT | 1.0513 | 1.0528 | -0.00155 | [-0.01399,0.01088] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_INHERIT_MATCH | 1.0513 | 1.0435 | 0.00777 | [-0.00518,0.02073] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_ODD_EVEN | 1.0513 | 1.0482 | 0.00311 | [-0.01865,0.02539] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_BIG_SMALL | 1.0513 | 1.0492 | 0.00207 | [-0.0057,0.01036] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_ZONE | 1.0513 | 1.0389 | 0.01244 | [0.0,0.02487] | 1.0 | 1.0 | INCONCLUSIVE |
| NO_SUM_SPAN | 1.0513 | 1.043 | 0.00829 | [-0.01036,0.02694] | 1.0 | 1.0 | INCONCLUSIVE |

## Strategy Diagnosis (STEP 19)

Why A/B/D did not beat random (from P2-2 + P3-3 evidence): no single-number feature shows OOS-robust, null-beating discrimination (all front AUC ≈ 0.5 and many invert below 0.5), and the D ablation shows removing any one statistical feature does NOT raise OOS hit rate (all deltas ≈ 0, Holm not significant). => NO IDENTIFIABLE PREDICTIVE FEATURE; the strategies are entertainment selectors over non-predictive history, so they cannot beat the invariant random baseline.

## Feature Decisions

SUPPORTED: NONE
UNSUPPORTED: ['back_hot', 'back_in_prev', 'back_max_omit', 'back_recent_ratio', 'back_trend', 'front_recent_ratio']
REDUNDANT: ['back_avg_omit', 'back_cur_omit', 'back_freq_ratio', 'back_omit_ratio', 'front_avg_omit', 'front_cur_omit', 'front_freq_ratio', 'front_hot', 'front_omit_ratio']
INCONCLUSIVE: 28 items (incl. most single features + D ablations)

## Final Answers

FRONT FREQUENCY SUPPORTED: False
FRONT OMISSION SUPPORTED: False
FRONT HOT/COLD SUPPORTED: False
BACK FREQUENCY SUPPORTED: False
BACK OMISSION SUPPORTED: False
STRUCTURE SUPPORTED: False
D FULL MEAN: 1.0513
D BEST ABLATION (highest post-removal OOS mean = possibly-harmful feature): NO_MISSING -> 1.0725 (FULL 1.0513, adj p=1.0)
ANY FEATURE CONFIRMED ON FINAL HOLDOUT: NO
ANY D ABLATION CONFIRMED: NO
IDENTIFIABLE PREDICTIVE FEATURE: NO (none beats null + holdout)
ML JUSTIFIED BY FEATURE EVIDENCE: NO (base features lack stable OOS signal → ML only adds overfit space)

## Production Integrity

- PRODUCTION ALGORITHM CHANGED: NO
- PRODUCTION CAP CHANGED: NO (recent_issues=1000)
- 26112 SNAPSHOT CHANGED: NO (hash bea8ef87f3f13723)
- PUSH: NO / DEPLOY: NO

## Tests

tests/test_p33_feature_study.py (run before commit)
