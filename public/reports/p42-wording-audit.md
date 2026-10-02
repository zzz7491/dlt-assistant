# P4-2 WORDING AUDIT

Scope: user-visible production copy only (public/ + src front-end text generators).
Product semantics (frozen): DLT = 大乐透历史数据分析 + 娱乐推荐工具, NOT a
lottery prediction system. P2/P3 research CLOSED: no confirmed predictive edge.

## Classification legend
- A = legitimate historical-research / disclaimer wording (KEEP)
- B = misleading current-product predictive claim (FIX)

## Findings

| # | file | line | current wording | class | reason | proposed replacement |
|---|------|------|-----------------|-------|--------|----------------------|
| 1 | public/experiment.html | 98 | 预测目标期号： | B | "预测目标" implies forecasting the next draw's target; this is an entertainment-recommendation period label | 娱乐推荐目标期号： |
| 2 | public/experiment.html | 138 | 预测次数 (table header) | B | "预测次数" implies predictions were made; it is a backtest repeat count | 回测次数 |
| 3 | public/experiment.html | 138 | 胜随机 (table header) | B | "胜随机" displays as a WIN/edge claim; research found models NOT distinguishable from random | 相对随机基线 |
| 4 | public/experiment.html | 74 | 每日实验预测任务 | B (mild) | "预测任务" labels the experiment pipeline as predictive | 每日实验任务 |
| 5 | public/experiment.js | 193 | headers "预测次数" / "胜随机" | B | JS-generated rank table headers repeat #2/#3; must stay consistent with HTML | 回测次数 / 相对随机基线 |
| 6 | public/experiment.js | 215 | 「胜随机」基于综合评分的微小差异…不构成显著证据…非预测 | A | already a qualified disclaimer explaining 胜随机 is NOT significant evidence | KEEP |
| 7 | public/experiment.html | 132 | 含随机基准，用于检验模型是否优于随机 | A | legitimate research framing ("test whether better than random") | KEEP |
| 8 | public/experiment.html | 158 | 不衡量预测能力…差异可能仅为随机噪声 | A | disclaimer / entertainment framing | KEEP |
| 9 | public/experiment.html | 200 | 不构成中奖预测…负期望游戏…理性购彩 | A | strong disclaimer | KEEP |
| 10 | public/index.html | 73 | 娱乐推荐，不等于中奖预测 | A | required exactly-one-final-recommendation disclaimer | KEEP |
| 11 | public/index.html | 36/109 | 不具备预测彩票结果能力 | A | strong disclaimer | KEEP |
| 12 | src/experiment_scheduler.py | 5,355 | 预测目标期 (code comment/docstring) | A (out-of-scope) | research-layer source comment, not user-visible production copy; P4-2 = user-visible wording only | no change (minimal diff; do not touch research script) |

## Notes
- "模型" retained as-is where it refers to analysis strategies (v1/v2/adaptive/random
  are analysis strategies, not forecasting models). No layout/CSS/JS-logic/API change.
- exactly-one-final-recommendation semantics (index.html #70 "本期唯一推荐",
  A/B/C/D internal-only) must be preserved.
- 26112 / 26113 snapshots are untouched by wording edits.
