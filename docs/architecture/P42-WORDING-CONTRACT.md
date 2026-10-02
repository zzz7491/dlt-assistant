# P4-2 PRODUCTION WORDING INTEGRITY — 文案契约

## 目的

本任务**不是**提升预测能力，而是让生产用户可见文案与 P2/P3 已关闭的研究
结论一致：

> 大乐透历史数据分析 + 娱乐推荐工具，**不是**彩票预测系统。

研究结论（P2/P3 CLOSED）：
- PREDICTIVE EVIDENCE = NOT CONFIRMED
- IDENTIFIABLE PREDICTIVE FEATURE = NO
- ROBUST SELECTOR EDGE = NO
- ML JUSTIFIED = NO

任何当前产品文案不得暗示"本工具能预测下一期 / 提高中奖率 / 战胜随机 /
存在预测优势"。

## 允许表达（A 类：历史研究 / 免责 / 娱乐分析）

历史数据分析、历史统计、娱乐推荐、随机基线、回测、实验、研究、
历史表现、历史命中、历史评估、**未确认预测能力**、**不构成预测**、
**不保证中奖**、负期望游戏、理性购彩、"本期唯一推荐（娱乐）"。

否定/免责语境下的"预测"是**允许**的，例如：
"不构成中奖预测"、"非预测目标"、"不衡量预测能力"、"不代表真实预测模型"、
"未确认优于随机基线"。

## 禁止作为当前产品能力声称

预测下一期、预测号码、模型预测能力、提高中奖率、稳定战胜随机、
存在预测优势、高概率中奖、AI 能预测彩票、推荐具有统计预测能力、
保证中奖 / 必中 / 稳赢。

## "推荐"的用法

可保留"推荐"，但必须属于**娱乐推荐 / 分析展示**，不得暗示预测保证。
index.html 必须保留 **exactly ONE FINAL RECOMMENDATION**（"本期唯一推荐"），
A/B/C/D 为 internal-only 后台候选，不呈现给用户做选择。

## 本次 P4-2 措辞映射（experiment page）

| 旧 | 新 | 类别 |
|---|---|---|
| 预测目标期号： | 娱乐推荐目标期号： | B→限定 |
| 模型：（推荐区标签） | 分析策略： | B→中性 |
| 预测次数（表头） | 回测次数 | B→中性 |
| 胜随机（表头） | 相对随机基线 | B→限定 |
| 排行榜 badge "胜" | "略优"（列名已限定） | B→弱化 |
| "「胜随机」…不构成显著证据" | "「相对随机基线」…未确认优于随机基线" | A 免责改写 |
| 每日实验预测任务 | 每日实验任务 | B→中性 |

保留不变：所有强免责声明（不构成预测 / 非预测 / 负期望 / 理性购彩 /
"不等于中奖预测"）、index.html 唯一推荐语义、所有 JS/data hooks 与数据字段名。

## 范围与禁令

- 仅改用户可见文案（public/*.html + public/*.js 文案串）。
- **不改**：布局、CSS（除非文字长度必要小修）、JS 数据逻辑、API、
  recommendation generation、publication schema、recommender/scoring/weights/
  analysis-window、immutable snapshot（26112 / 26113）。
- 不引入新预测承诺；"预测"仅可在否定/免责/历史研究语境出现。

## 验证

`tests/test_p42_wording_integrity.py`（12 断言）：
无未限定预测承诺、无"胜随机"裸表头、免责声明存在、娱乐框架存在、
无"保证中奖"、唯一推荐语义保留、关键 JS/data hooks 未丢、
JS 表头改名、JS 数据字段未改、index 免责、snapshot 文件完整。

机器可审计 regression：`reports/p42-wording-audit.json`。
