# Phase 16 Step 4 报告 — 实验展示层（模型研究 + 娱乐价值实验）

> 日期：2026-08-28
> 性质：**实验层 · 非生产**。严格遵循「只读维护」纪律——不修改生产推荐链路、不修改生产 `recommendations.json`、不把实验结果包装成「提升中奖率」证据。
> 一句话结论：本步骤把 Phase 15 + Phase 16 的全部实验结论**诚实、可溯源、可降级**地接入 `experiment.html`，并显式声明「无统计证据支持自动调权」。

---

## 1. Step 1 只读检查（Read-only Check）

执行前逐文件只读检查，未对任何生产文件做任何修改，仅读取以确认字段结构：

| 类别 | 文件 | 关键确认 |
|------|------|----------|
| 页面 | `public/experiment.html` / `public/experiment.js` | 既有区块结构、DOM 容器 id、加载方式 |
| 样式 | `public/experiment.css` / `public/style.css` | 既有 token（`--accent #6d28d9` 等），决定新增区块沿用同套样式 |
| Phase 15 排行榜 | `reports/model_ranking.json` | canonical 900 期；ranking=[v1, adaptive, random, v2]；权重 hit0.4/cov0.35/stab0.25；beats_random={v1:true, v2:false, adaptive:true, random:false} |
| Phase 15 特征增益 | `reports/feature_gain_report.json` | 特征增益排序（用于「模型研究总览」） |
| Phase 15 诊断 | `reports/model_diagnostic_report.json` | chi2 全部 `distinguishable_from_random=false`；最大 cosine=0.969（模型间高度相似） |
| Phase 15 奖励稳定性 | `reports/reward_stability_report.json` | 含 900 长度 `cumulative_profit_series`（展示层需裁剪）；全部 ROI 为负 |
| Phase 15 反事实 | `reports/counterfactual_analysis.json` | 仅 2 个变体 `significant=true`，但被标记为 exploratory（探索性，非结论） |
| Phase 15 娱乐评估 | `reports/entertainment_evaluation.json` | adaptive `rolling20_front_coverage_mean=0.5201` vs random `0.9992`；v1 `longest_miss_streak=25`，`anti_miss_streak` 组件分=0.64 |
| Phase 16 Step2 | `reports/entertainment_constrained.json` | 6 期单测产物（仅作数据溯源，不展示为结论） |
| Phase 16 Step3 | `reports/phase16_step3_validation.json` | 多窗口×多种子 12 组合；aggregate coverage_boost pass_rate=0.5 / 小奖不降率=0.5 / mean_ux_delta=-0.0924；`validity.affects_step3_results=false`；`coverage_boost_stable=false` |
| 旧展示数据 | `public/data/model_ranking.json` | 旧 6 期单测产物——**已被本次生成的 900 期版本覆盖** |
| 现有 API | `functions/api/model/status.ts` | 读取 `/data/model_status.json`；本次**未改动 API**（改用静态 `public/data/*.json` 兜底，零生产变更） |
| 状态 | `TASK_STATUS.md` | Phase 16 Step 3 段已完成，确认可进入 Step 4 |

**纪律确认**：未猜测任何字段结构，全部以真实 JSON + 页面代码为准。

---

## 2. 变更 / 新增文件

### 新增（实验层 + 可复现生成器 + 测试）
- `scripts/build_experiment_display_data.py` — **可复现生成器**：从 `reports/*.json` 派生 7 个展示用 JSON（裁剪 900 长度 `cumulative_profit_series`，Step3 加 `combos[]` 紧凑网格）。下次重跑即可重建全部展示数据。
- `tests/_page_step4_dom.cjs` — 纯 Node DOM 桩（无 jsdom 依赖），加载 `public/experiment.js` 触发渲染，两种模式：全 JSON 正常 / `FAIL_FILE=phase16_step3_validation.json` 模拟 404 降级。
- `tests/test_phase16_step4.py` — pytest：覆盖全部 JSON 加载、缺失 JSON 降级、random 基线展示、Step3 validity/caveat、`coverage_boost=不稳定`、无「自动调权已启用」伪状态。

### 全量重写（仅扩展研究层，未动生产渲染逻辑）
- `public/experiment.js` — 在既有 `renderRecommendations/renderStatus/renderAnalysis/renderRanking` 之外，**新增非阻塞研究层**：`safeFetch`、`makeTable`、`verdictTag`、`renderModelOverview`、`renderDiagnostics`、`renderEntertainment`、`renderCounterfactual`、`renderStability`、`renderWhyNoAutoTune`、`loadResearch()`。原页面加载函数顺序调用新增 `loadResearch()`，任一区块失败不影响既有页面。
- `public/experiment.html` — 按要求的 9 个区块顺序重排并新增 id（`sec-overview`→`sec-live`→模型状态→推荐解释→`sec-overview-models`→`sec-ranking`→`sec-diagnostics`→`sec-entertainment`→`sec-counterfactual`→`sec-stability`→`sec-no-autotune`→`sec-method`）；新增内联 CSS（`.verdict`/`.caveat-box`/`.flag-list`/`.method-list`/`.big-statement` 等），沿用既有配色 token。

### 生成（静态展示数据，非生产）
- `public/data/model_ranking.json`（覆盖旧 6 期版，改为 900 期 canonical）
- `public/data/phase15_model_diagnostics.json`
- `public/data/phase15_feature_gain.json`
- `public/data/phase15_reward_stability.json`
- `public/data/phase15_counterfactual.json`
- `public/data/phase16_entertainment.json`
- `public/data/phase16_step3_validation.json`

### 文档
- `reports/Phase16-Step4-Report.md`（本文件）
- `TASK_STATUS.md`（追加本段）

**未触碰**：`src/scorer.py`、`src/recommender.py`、`src/scheduler.py`、`src/publisher.py`、`data/recommendations.json`（生产）、`functions/api/*`（API 未改）。

---

## 3. 页面功能（Page Functions）

`experiment.js` 新增研究层职责：

| 函数 | 渲染区块 | 关键诚实约束 |
|------|----------|--------------|
| `renderModelOverview(ranking, diag)` | 模型研究总览 | 明确标注 **random 是基线锚点而非真实模型**；展示模型间相似度（max cosine 0.969） |
| `renderModelRanking`（既有） | 模型排行榜 | 沿用 canonical 900 期排名与复合权重（hit0.4/cov0.35/stab0.25，非 ROI-only） |
| `renderDiagnostics(diag, rs)` | 模型诊断 + 奖励稳定性 | chi2 全部不可区分于随机；奖励稳定性全部 ROI 为负，显式说明「无正收益」 |
| `renderEntertainment(ent)` | 娱乐价值 | **注入两条硬编码诚实提示**：① adaptive 覆盖率 0.5201 ≪ random 0.9992（覆盖不足问题）；② v1 最长空军 25 期（`anti_miss_streak` 组件分 0.64，空军体验差） |
| `renderCounterfactual(cf)` | 反事实实验 | 三块（特征消融 / 策略移除 / 集成对比）；**同时展示不显著变体**，仅 2 个标 `significant=true` 且标注 exploratory |
| `renderStability(step3)` | 稳定性验证 | 聚合表 + **`coverage_boost = 不稳定` 红旗横幅** + caveat 框（来自 `validity`）+ combos 表 |
| `renderWhyNoAutoTune(...)` | 为什么没有自动调权 | 同时解释 Phase 15（模型无统计区分度）与 Phase 16（coverage_boost 不稳定）原因，**结尾明确「无统计证据支持自动修改权重」** |

每个区块独立 `safeFetch` + 独立 try/catch + 失败兜底说明：缺任一 JSON 文件只会让对应区块显示「数据缺失」提示，页面其余部分正常。

---

## 4. 数据来源（Data Sources）

- **主路径**：`public/data/*.json` 静态兜底文件（由 `scripts/build_experiment_display_data.py` 从 `reports/*.json` 可复现生成）。
- **不改动生产 API**：`functions/api/model/status.ts` 仍只读 `/data/model_status.json`；本次未新增/修改任何 API，展示层完全走静态文件，零生产链路变更、零泄露未来数据风险。
- **可溯源**：每个展示字段均可回溯到 `reports/` 下的具体实验产物；生成器脚本保留在 `scripts/` 便于复核与重建。
- **失败兜底**：每个 fetch 均非阻塞、失败返回 `null` 并渲染兜底说明，缺失单文件绝不导致整页崩溃。

---

## 5. 测试结果（Test Results）

- **Step 4 专属测试**：`pytest tests/test_phase16_step4.py` → **13 passed**（7 个数据文件结构校验 + Step3 validity 标记 + HTML 区块存在 + 诚实文案/无伪状态 + JS 语法 `node --check` + DOM 全 JSON 正常 + DOM 缺失单 JSON 降级）。
- **完整套件**：`pytest tests/` → **308 passed / 1 failed**。
  - 唯一失败：`tests/test_phase14_step3.py::test_load_data`（断言 `issues[0].issue=="19132"`，而当前 `data/dlt_history.json` 最新期号已更新为 `19134`）。属**历史既有失败**（前序阶段数据刷新导致，与本次实验展示层无关），非 Step 4 回归。
- **DOM 桩关键断言**（验证诚实展示）：错误框隐藏、random 基线正确展示、adaptive 覆盖不足提示展示、`coverage_boost=不稳定` 展示、页面**不出现「自动调权已启用」**伪状态。

---

## 6. 生产隔离验证（Production Isolation）— 强制检查

执行前记录 baseline，执行后复查：

| 检查项 | Baseline（Step1 记录） | 执行后 | 结果 |
|--------|------------------------|--------|------|
| `src/scorer.py` mtime | 1787392208 | 1787392208 | ✅ 一致 |
| `src/recommender.py` mtime | 1787733209 | 1787733209 | ✅ 一致 |
| `src/scheduler.py` mtime | 1787733140 | 1787733140 | ✅ 一致 |
| `src/publisher.py` mtime | 1787420380 | 1787420380 | ✅ 一致 |
| `data/structure_profile.json` SHA256 | `ef67895429f4d742a88b21767701073df7cb51cd767f7281abaac7a476207cac` | `ef67895429f4d742a88b21767701073df7cb51cd767f7281abaac7a476207cac` | ✅ 完全一致 |

结论：生产算法层、调度层、发布层、生产推荐文件、canonical 结构画像均**未被本次改动触碰**。

---

## 7. Phase 15 + 16 最终结论（Final Conclusions）

**Phase 15（模型研究）**
- 复合评分（hit0.4 / coverage0.35 / stability0.25）排名：v1 > adaptive > random > v2；仅 v1、adaptive 显著优于随机，v2 未显著优于随机。
- 模型诊断：所有模型 chi2 不可区分于随机；模型间最大余弦相似度 0.969（高度相似，无本质区分度）。
- 奖励稳定性：全部 ROI 为负，无正收益策略。
- 反事实：仅 2 个变体 p<2σ「显著」，但明确标记为 exploratory（探索性），不构成结论性证据。

**Phase 16（娱乐约束优化）**
- Step2：三种约束变体（coverage_boost / diversity_boost / miss_streak_breaker）在单窗口回放中 UX 高于 baseline 且小奖频率未降——但属「结构约束扩大覆盖→更多接近中奖」，**非预测能力**，且需全量+多种子复核。
- Step3：多窗口（200/500/900）× 多种子（1/42/123/999）12 组合验证 → **coverage_boost 不稳定**（pass_rate=0.5<0.75；小奖不降率=0.5<0.917；mean_ux_delta=-0.0924；`coverage_boost_stable=false`）。差异大概率仅为随机噪声，**不接入 `experiment.html` 作为结论策略**。
- 诚实暴露的两类体验问题：① adaptive 覆盖率仅 0.5201（随机 0.9992），覆盖严重不足；② v1 最长空军 25 期，空军体验差。

---

## 8. 无法做到的事（What Cannot Be Done）

- ❌ **不能宣称提升中奖率**：所有实验均为历史回测/结构约束效果，模型间差异可能仅为随机噪声；页面无任何「提高中奖概率」文案。
- ❌ **不能自动调权**：Phase 15（模型无统计区分度）+ Phase 16（coverage_boost 不稳定）均无统计证据支持修改 `src/scorer.py` 的权重；页面「为什么没有自动调权」明确收尾「无统计证据支持自动修改权重」。
- ❌ **不能把 coverage_boost 当结论策略展示**：Step3 已判不稳定，仅作为「不稳定」警示呈现，不作推荐。
- ❌ **不能改动生产推荐链路**：scorer/recommender/scheduler/publisher、`data/recommendations.json`、API 均保持冻结（见第 6 节）。
- ❌ **不能把反事实 2σ 结果当定论**：明确标注 exploratory，避免误导。

---

## 9. 下一步建议（Next-Step Suggestions）

1. **展示层上线**：建议将本次 `public/` + `public/data/` + `scripts/` + `tests/` 提交后，经 GitHub Actions 部署到 Cloudflare Pages 的 `experiment.html`，供用户审阅诚实实验结论。
2. **数据刷新一致性**：建议统一 `data/dlt_history.json` 期号口径（修复历史失败的 `test_load_data` 硬编码 `19132`→动态取值），避免历史测试误报。
3. **持续监控**：保留 `loadResearch()` 的非阻塞+降级设计；若未来 `reports/*.json` 字段变更，仅需更新生成器与对应 render 函数，不影响既有页面。
4. **未启动 v2.0 / V3 / V4**：保持现有稳定架构运行；自动调权、走势图系统、用户体系等均在规划文档中、当前不开发。
5. **复核门槛（若未来要做）**：任何「约束变体接入生产展示」都需先满足稳定性阈值（pass_rate≥0.75、小奖不降率≥0.917、mean_ux_delta>0）且多种子复核，方可考虑——当前未达。
