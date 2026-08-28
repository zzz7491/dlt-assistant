# 当前项目状态

## 当前阶段

**Phase**: Phase 10 - 数据降级与恢复机制  
**Task**: Task #36-R.8 首页展示恢复与验收  
**Status**: ✅ Phase 10 Recovery R5.3 人工验收通过（R5.2 修复确认有效，生产页面正常，基线仍冻结于 production-stable-v1.0）

---

## 当前稳定版本

| 项目 | 值 |
|-----|-----|
| **Git Commit** | `36d9bfc` |
| **日期** | 2026-08-22 13:09 |
| **状态** | 🟢 生产可用 |
| **描述** | Phase 10 Recovery R3.2 首页生产稳定基线（含 index.html 错误提示修复 a1e7e35） |

---

## 生产稳定基线 (Phase 10 Recovery R4 冻结)

**确认时间**: 2026-08-22 21:15  
**当前稳定基线**: `production-stable-v1.0`  
**生产地址**: `https://500wan.mootlsv.com/`

### 稳定基线记录

| 项目 | 值 |
|------|-----|
| **Git Commit** | `36d9bfc`（含 `a1e7e35` 修复） |
| **Cloudflare Deployment** | `32574914238`（大乐透 AI 娱乐分析，success） |
| **URL** | https://500wan.mootlsv.com/ |
| **标签说明** | Phase 10 Recovery R3.2 homepage production stable baseline |

### 验证项目

- ✅ **首页加载**：index.html 200，第 52 行显示 `data/recommendations.json`（非 final_recommendation.json）
- ✅ **JS 加载**：`public/app.js` 200，application/javascript
- ✅ **JSON 加载**：`data/recommendations.json` / `data/dlt_history.json` 均 200
- ✅ **推荐数据显示**：4 策略 (A/B/C/D) 完整渲染
- ✅ **Console 无错误**：R3.2 部署后生产验证通过

### 基线资源确认

| 资源 | 状态 | HTTP | 说明 |
|-----|------|------|------|
| 首页 index.html | 🟢 | 200 | CDN 正常 |
| `public/app.js` | 🟢 | 200 | application/javascript |
| `data/recommendations.json` | 🟢 | 200 | application/json, 4 策略完整 |
| `data/dlt_history.json` | 🟢 | 200 | application/json, 历史数据完整 |

### 基线特征状态

| 功能 | 状态 | 说明 |
|-----|------|------|
| 首页推荐展示 | ✅ 正常 | 4 策略 (A/B/C/D) 完整展示 |
| 历史数据加载 | ✅ 正常 | 1000 期大乐透开奖历史 |
| 冷热号分析 | ✅ 正常 | 统计数据完整 |
| 走势图 | ✅ 正常 | 图表展示正常 |

### 禁止修改区域

- ❌ **算法层**: `src/` 目录推荐算法
- ❌ **数据生成层**: 推荐生成逻辑
- ❌ **产品逻辑**: 首页展示逻辑
- ❌ **UI 样式**: 现有页面样式
- ❌ **数据结构**: 现有 JSON 文件格式

**原则**: 只读维护，不新功能开发，保持生产稳定

### 回滚方案

- **回滚命令**: `git reset --hard production-stable-v1.0`
- **回滚标签**: `production-stable-v1.0`（指向 `36d9bfc`）
- **部署方式**: GitHub Actions 自动部署
- **验证地址**: `https://500wan.mootlsv.com/`

---

## 最近完成任务

---

## 最近完成任务

### Task36-R8: 首页恢复最终验收

**完成内容**:
- ✅ 回退 `public/app.js` 到稳定版本 (72e9e35^)
- ✅ 移除 `final_recommendation.json` 依赖
- ✅ 恢复 `recommendations.json` 数组格式加载
- ✅ 本地验证通过 (HTTP 8888)
- ✅ GitHub Actions 部署完成
- ✅ 线上验证通过 (`https://500wan.mootlsv.com/`)

### Phase 10 Recovery R2: 生产稳定基线确认

**完成内容**:
- ✅ Git 只读检查 (status, log, remote 验证)
- ✅ 生产资源 HTTP 验证 (HTML/JS/JSON 全部 200 OK)
- ✅ CDN 缓存问题定位 (max-age=14400)
- ✅ 触发 GitHub Actions 重新部署 (空提交 `1de051d`)
- ✅ 部署成功确认 (`大乐透 AI 娱乐分析` completed success)
- ✅ 修复 `index.html` 错误提示 (Commit `a1e7e35`)
- ✅ 生成验收报告 `Phase10-R2-生产稳定基线验收报告.md`
- ✅ 更新记忆文件 `.workbuddy/memory/2026-08-22.md`

**当前状态**: 等待用户清除浏览器缓存后重新验证

**验证结果**:
- ✅ 首页 200 + CDN 响应
- ✅ `recommendations.json` 4 策略完整加载
- ✅ `app.js` + 历史数据正常
- ✅ 无 JS 报错
- ✅ 兼容性确认通过

---

### Phase 10 Recovery R3.2: 部署触发与生产环境验证

**完成内容**:
- ✅ 诊断 workflow `32547242570` 失败根因（Git push 被拒绝导致 `wrangler pages deploy` 未执行）
- ✅ 同步本地 HEAD 至 `bf4b7cb`，创建空提交 `36d9bfc` 触发部署
- ✅ 手动触发 workflow_dispatch `32574914238`（success）
- ✅ `wrangler pages deploy` 成功执行（部署到 Cloudflare Pages）
- ✅ 生产域名 `https://500wan.mootlsv.com/` 第 52 行恢复为 `recommendations.json`
- ✅ 生成验收报告 `task10-recovery-r3.2-deployment.md`

**验证结果**:
- ✅ index.html 200 + 错误提示正确
- ✅ app.js / recommendations.json / dlt_history.json 全部 200
- ✅ 生产环境恢复正常

---

### Phase 10 Recovery R4: 生产稳定基线冻结

**完成内容**:
- ✅ Step 1 只读检查（AGENTS.md / TASK_STATUS.md / CHANGELOG.md + Git/Cloudflare/域名验证）
- ✅ Step 2 建立稳定标签 `production-stable-v1.0` → `36d9bfc`（强制更新，含 R3.2 修复）
- ✅ Step 3 完善 TASK_STATUS.md 稳定基线记录
- ✅ Step 4 更新 CHANGELOG.md（Phase 10 Recovery R3.2 段）
- ✅ Step 5 生成恢复报告 `reports/phase10-production-stable-v1.0.md`
- ✅ Step 6 建立以后修改规则（7 步流程 + 禁止项）
- ✅ Step 7 输出最终生产状态

**基线版本**: `production-stable-v1.0` = `36d9bfc`
**状态**: 🟢 已冻结，等待用户确认后才可进入下一阶段开发

### Phase 10 Recovery R5: 生产监控与自动验收基础建设

**状态**: ✅ 已完成（监控基础已建 + R5.2 修复 + R5.3 人工验收通过）

**完成内容**（本阶段仅建设监控/验证工具，禁止修改首页/算法/UI/数据结构）:
- ✅ Step 1 只读检查（AGENTS/TASK_STATUS/CHANGELOG + Git/Cloudflare/域名验证）
- ✅ Step 2 部署链路确认（GitHub→Actions→wrangler pages deploy→dlt-assistant→500wan.mootlsv.com）
- ✅ Step 3 新增生产检查脚本 `scripts/check-production.sh`（首页/资源/内容/JS/JSON 校验，PASS/FAIL 退出码）
- ✅ Step 4 版本标识方案设计 `docs/production-version-design.md`（推荐方案 B: version.json，待用户确认实施）
- ✅ Step 5 新增回滚说明 `docs/ROLLBACK.md`
- ✅ Step 6 更新工程记录（本段）
- ✅ Step 7 Git 提交（chore: add production monitoring foundation）
- ✅ Step 8 输出完成报告

**禁止修改区域（本阶段硬性约束）**:
- ❌ 首页业务逻辑 / 推荐算法 / 数据结构 / UI / 生产页面功能 / 一期一注

**下一步**: 等待用户确认版本标识实施方案（方案 B 推荐）后，再决定是否实施 version.json

---

### Phase 10 Recovery R5.2: 生产运行错误修复（Hotfix）

**状态**: ✅ 已完成

**完成内容**:
- ✅ Step 1 只读检查（确认基线 `production-stable-v1.0` → `36d9bfc`，修复前 master = `d1679f4`）
- ✅ Step 2 备份状态（git status / branch / commit 记录，确认未提交改动范围）
- ✅ Step 3 最小修复（仅 2 文件 +7/-2）：
  - `public/index.html`：在「本期智能推荐」区块补充 `<span id="rec-target">—</span>`（展示预测期号，保持原布局）
  - `public/app.js`：第 272 行增加 null 防护（`var recTargetEl = ...; if (recTargetEl) ...`）
  - `public/app.js`：渲染主流程外包 try/catch 安全网（任何 DOM 查询失败优雅降级，不白屏）
- ✅ Step 4 本地验证（`python -m http.server` + Node DOM 桩执行渲染逻辑，正常 / 缺元素两种场景均无 TypeError，推荐数据正常渲染）
- ✅ Step 5 Git 提交 `8d33a15`（fix: repair homepage recommendation render crash）
- ✅ Step 6 正式部署（`wrangler pages deploy` 实际执行成功 → 部署至 dlt-assistant master → 绑定 500wan.mootlsv.com）
- ✅ Step 7 生产验证（生产版 app.js + 生产数据 Node 执行无异常；全部资源 200；首页含 rec-target）
- ✅ Step 8 更新工程记录（本段 + CHANGELOG）

**修复前后**:
- 修复前：`app.js:272` 对 null 赋值 → `TypeError: Cannot set properties of null` → 渲染中断 → 首页无推荐数据
- 修复后：首页正常显示最新开奖（26094期）+ 推荐策略 + 预测期号 26095

**严禁项遵守**: 未重新设计首页 / 未改推荐算法 / 未改数据结构 / 未改 UI 布局 / 未新增功能（仅最小热修复）

**回滚方法**:
- `git revert 8d33a15`（保留基线 `36d9bfc` 完好）后重新部署
- 或 `git checkout 36d9bfc -- public/` 还原两文件后部署

---

### Phase 10 Recovery R5.3: 生产恢复人工验收

**状态**: ✅ 已完成（用户人工验收通过）

**完成内容**:
- ✅ Step 1 只读确认当前运行版本（本地 HEAD / 远程 master = `a1661b9`；最新修复 commit = `8d33a15`；标签 `production-stable-v1.0` 仍指向 `36d9bfc`；生产实际代码已含修复痕迹）
- ✅ Step 2 等待用户打开 `https://500wan.mootlsv.com/` 人工检查（不修改、不部署）
- ✅ Step 3 提供人工验收清单（首页 / 数据显示 / 五个模块 / 控制台）
- ✅ Step 4 等待用户确认

**用户验收结论（2026-08-22 22:01）**:
- ✅ 首页正常打开，无 `Cannot set properties of null`
- ✅ 无红色错误提示
- ✅ 最新开奖数据（26094 期）+ 推荐区域 + 预测期号（26095）+ A/B/C/D 策略均正常显示
- ✅ 五个模块（首页 / 数据分析 / 智能选号 / 趋势分析 / 我的方案）切换正常
- ✅ Console 无 TypeError / 无 JavaScript error / 无 404 资源错误
- ✅ 确认 R5.2 修复有效

**严禁项遵守**: 未开发 R6 / 未增加自动化 / 未优化代码 / 未改首页设计 / 未改推荐算法 / 未改数据结构（仅做只读确认与文档记录）

---

---

### Phase 16 Step 2: 娱乐约束优化实验层（实验层 · 非生产）

**状态**: ✅ 已完成（仅实验层，生产链路未改动）

**完成内容**:
- ✅ Step 1 只读检查：确认 `select_top_n`（`topn_selector.py:81`）按 `total_score` 重排为约束注入点；候选池来自 `generate_candidates`，结构画像写临时文件避免污染 canonical。
- ✅ Step 2 新增 `src/entertainment_constrained_runner.py`：walk-forward 回放，每期共享候选池，四种策略（baseline / coverage_boost / diversity_boost / miss_streak_breaker）+ random 锚点。
- ✅ Step 3 测试 + 实跑 + 生产隔离确认：
  - `tests/test_phase16_step2.py` 3 passed；完整套件 293 passed / 1 既有失败（与本次无关）。
  - 回放 200 期：三种变体 UX 均高于 baseline 且小奖频率未降（coverage_boost ΔUX+0.1485 / diversity_boost +0.0663 / breaker +0.0389，全部通过）。
  - 生产 4 文件 mtime 未变；`data/structure_profile.json` 未被污染。
  - 产物：`reports/entertainment_constrained.json` + `reports/Phase16-Step2-Report.md`。

**诚实结论**: 提升来自结构约束（更广覆盖 → 更多接近中奖），非预测能力；coverage_boost 小奖频率增益需全量+多种子复核后才考虑作为实验展示策略。

**下一步**: 待用户确认是否复核或接入 `experiment.html`（不替换生产推荐）。

---

### Phase 16 Step 3: 娱乐约束优化长期稳定性验证（实验层 · 非生产 · 已完成）

**目标**: 验证 coverage_boost 在 **多窗口（200/500/900 期，取最近 N 期 tail=True）× 多种子（1/42/123/999）** 下是否稳定「不降低小奖频率」且「提升多样性/覆盖率/UX」。

**完成内容**:
- ✅ 全量验证完成（12 组合）：`reports/phase16_step3_validation.json`。
- ✅ 稳定性结论：**coverage_boost 不稳定**（pass_rate=0.5<0.75，小奖频率不降率=0.5<0.917，平均 ΔUX=-0.0924）→ 不接入 `experiment.html`。差异大概率仅为随机噪声。
- ✅ 隔离收尾（用户追加）：发现并修复 `structure_profile.json` 污染。
  - 根因：`generate_structure_profile` 默认 `output_path=canonical`；`tests/test_structure_profile.py`（MIN_ISSUES=10）与多个实验模块缺 `output_path` 直接命中默认。Step2 仅在 runner 内改 temp，是「点」不是「面」。
  - 修复：默认改 `SCRATCH_PROFILE_PATH`（temp），仅 `main()` 显式写 canonical；恢复 canonical 为全量 1000 期（SHA256 `ef678954…`）。
  - SHA256 实证：3 期小实验前后 canonical 完全一致；完整 pytest 跑完仍一致。
  - Step3 12 组结果判定 **VALID**（验证用 temp scratch，未受污染影响）；已向 JSON 加 `validity` 标记。
- ✅ 测试：`test_scorer_v2`+`test_structure_profile` 48 passed；完整 `pytest tests/` **295 passed / 1 failed**（唯一失败为既有 `test_load_data` 硬编码期号，无关）。
- ✅ 生产 4 文件 mtime 全程未变。

**纪律**: 不修改 scorer/recommender/scheduler/publisher；实验层结构画像只写 Temp/。

---

### Phase 16 Step 4: 实验展示层（模型研究 + 娱乐价值实验 · 实验层 · 非生产 · 已完成）

**目标**: 把 Phase 15 + Phase 16 全部实验结论**诚实、可溯源、可降级**地接入 `experiment.html`，显式声明「无统计证据支持自动调权」。

**完成内容**:
- ✅ Step 1 只读检查：`experiment.html/js/css`、`reports/model_ranking.json`、`feature_gain_report.json`、`model_diagnostic_report.json`、`reward_stability_report.json`、`counterfactual_analysis.json`、`entertainment_evaluation.json`、`entertainment_constrained.json`、`phase16_step3_validation.json`、`public/data/model_ranking.json`、现有 API `functions/api/model/status.ts`、`TASK_STATUS.md`。
- ✅ Step 2 新增可复现生成器 `scripts/build_experiment_display_data.py`：从 `reports/*.json` 派生 7 个展示 JSON（裁剪 900 长度 `cumulative_profit_series`，Step3 加 `combos[]`）。
- ✅ Step 3/4 重写 `public/experiment.js` + `public/experiment.html`：新增非阻塞研究层（`safeFetch`/`makeTable`/`verdictTag` + 7 个 render 函数），9 区块按顺序重排；adaptive 覆盖不足（0.5201 vs 随机 0.9992）与 v1 最长空军 25 期两条诚实提示硬编码注入；`coverage_boost=不稳定` 红旗横幅；「为什么没有自动调权」收尾「无统计证据支持自动修改权重」。
- ✅ Step 5 测试：`tests/test_phase16_step4.py` 13 passed；`tests/_page_step4_dom.cjs` DOM 桩验证（全 JSON 正常 / 缺失单 JSON 降级 / random 基线 / 覆盖不足提示 / coverage_boost=不稳定 / 无「自动调权已启用」伪状态）。
- ✅ Step 6 完整 `pytest tests/` **308 passed / 1 failed**（唯一失败为历史既有 `test_phase14_step3.py::test_load_data` 硬编码期号，与本次无关）。
- ✅ Step 7 生产隔离（强制）：4 生产文件 mtime 与 baseline 完全一致；`data/structure_profile.json` SHA256 `ef678954…` 前后一致。
- ✅ Step 8 Git 提交（仅实验层，不 push）：`public/experiment.js`、`public/experiment.html`、`scripts/build_experiment_display_data.py`、`tests/_page_step4_dom.cjs`、`tests/test_phase16_step4.py`、`public/data/*.json`（7 个）、`reports/Phase16-Step4-Report.md`、本段。
- ✅ Step 9 报告 `reports/Phase16-Step4-Report.md`（9 节）+ 本段 + 记忆更新。

**诚实结论**: 模型无统计区分度（chi2 全不可区分随机、max cosine 0.969）；奖励稳定性全 ROI 为负；反事实仅 2 变体 exploratory 显著；coverage_boost 多窗口多种子不稳定（pass_rate=0.5）→ 不接入为结论策略。全站无任何「提升中奖率」文案。

**纪律**: 未改 scorer/recommender/scheduler/publisher；未改 `data/recommendations.json`；未改 API；未把实验结果包装成预测/收益证据。

---

### Phase 16 Step 5: 实验数据自动更新流水线（实验层 · 非生产 · 已完成）

**目标**: 在「绝不修改生产逻辑 / 绝不修改生产推荐 / 生产冻结」前提下，让实验系统随每日开奖**自动运行 + 自动更新 + 增量计算 + 失败隔离 + 结果展示**。

**完成内容**:
- ✅ Step 1 只读检查（18 文件）：生产入口清晰隔离；实验层 0% 自动化；`experiments.sqlite` 已幂等（可复用，不改 `experiment_store`）；`build_experiment_display_data.py` 缺失容忍改造；`dlt-analysis.yml` 提交范围已覆盖实验数据（注入步骤 + 守卫，不冲突既有流程）。
- ✅ Step 2 三层自动化设计：daily（开奖后增量追加）/ weekly（walk-forward 重回放，数十分钟）/ manual（仅 `RECOMMENDATION_FOR_REVIEW.json`）。
- ✅ Step 3 新增 `src/experiment_scheduler.py`：`--daily/--weekly/--manual`；`last_processed_issue` 增量位点；每任务 `try/except` 失败隔离；运行记录 `data/experiment_runs.sqlite`（与实验数据分离）。
- ✅ Step 4 增量机制：`last_processed_issue` + `experiment_store` 幂等（`INSERT OR IGNORE` + 评估跳过已评估行）；覆盖 NO_NEW_DATA / issue 缺失 / 重复 / 倒退（不向后推进标记，已修复 meta 更新条件）/ 数据损坏 / recommendations 缺失 / SQLite 锁 / 模型缺失 / random 缺失 —— 均不影响生产。
- ✅ Step 5 `scripts/build_experiment_display_data.py` 容错改造：源报告缺失 → 写 `status=unavailable`；单文件异常隔离。
- ✅ Step 6 CI 注入 `dlt-analysis.yml`：日实验步骤 + 生产冻结 SHA 守卫（前/后快照 diff，不一致即 `exit 1` 阻断提交）；新增周日 `0 4 * * 0` cron + `workflow_dispatch` 输入 + `weekly-experiment` 作业（超时 90 分钟）。关键修正：`run_pipeline` 的 `generate_structure_profile` 默认落临时 scratch（非 canonical），故守卫对 `structure_profile.json` 不误触发。
- ✅ Step 7 失败隔离状态机：SUCCESS / PARTIAL_SUCCESS / NO_NEW_DATA / FAILED（BLOCKED_PRODUCTION_CHANGE 由 CI 守卫判定）。退出码：PARTIAL 仍 0，仅 FAILED 为 1，避免单实验失败阻断生产提交。
- ✅ Step 8 测试 `tests/test_phase16_step5.py` **14 passed**（增量 / 幂等 / 失败隔离 / 守卫 / 周任务 / 手动审阅-only 等）。
- ✅ Step 9 性能：daily 分钟级（不重放历史）；weekly ~65 分钟（独立作业 90 分钟超时）。
- ✅ Step 10 生产隔离复核：4 生产文件 mtime 与 Step 4 基线完全一致；`data/structure_profile.json` SHA256 `ef678954…` 一致；`data/recommendations.json` 仍 ABSENT。
- ✅ Step 11 完整 `pytest tests/` **322 passed / 1 failed**：唯一失败为历史既有 `test_phase14_step3.py::test_load_data`（硬编码期号，与本次无关），**无新增回归**。
- ✅ Step 12 最终验证通过。
- ✅ Step 13 报告 `reports/Phase16-Step5-Report.md`（12 节）。
- ✅ Step 14 Git 提交（仅实验层文件，不触碰既有未提交生产修改、不 push）。

**纪律**: 未改 scorer/recommender/scheduler/publisher；未改 `data/recommendations.json` 生成规则；未写 `config/adaptive_weights.yaml`；未把实验结果包装成预测/收益证据；全部为增量/加法，未删除既有函数。

---

### Phase 16 Step 6: 实验运行状态监控 + 数据质量护栏（实验层 · 非生产 · 已完成）

**目标**: 在零改生产/零改既有实验算法前提下，补齐两类可观测性缺口——「实验是否真的自动运行了」「实验使用的数据是否可靠」。

**完成内容**:
- ✅ Step 1 只读检查：生产冻结基线门通过（`structure_profile.json` SHA `ef678954…` 逐字节一致）；`experiment_runs.sqlite` 当时 ABSENT（运行监控数据从未产生）。
- ✅ Step 2 目标：L 运行状态监控 + M 数据质量监控（均属允许范围，ADD-ONLY）。
- ✅ Step 3 设计：monitor 只读 `experiment_runs.sqlite`、data_quality 只读 `data/dlt_history.json`；仅写 `reports/experiment_*.json` + `public/data/experiment_*.json`；不 import/调用任何生产模块。
- ✅ Step 4 实现：
  - 新增 `src/experiment_monitor.py`：聚合 run_log+meta → `reports/experiment_run_status.json`；处理库不存在/空/损坏(DatabaseError)/意外 → `unavailable/error` 结构化降级，绝不崩溃。
  - 新增 `src/experiment_data_quality.py`：9 项检查 → `reports/experiment_data_quality.json`；`ok/degraded/error`；年界缺口如实标注「需人工确认」，不臆断缺失。
  - `scripts/build_experiment_display_data.py` ADD-ONLY 新增两步（run_status / data_quality），沿用 existing `unavailable` 容错。
  - `experiment.html` 新增 `#sec-health`；`experiment.js` 新增 `renderHealth()` + `loadHealth()`（非阻断，失败仅本区块 unavailable）。
  - `dlt-analysis.yml` 在 analyze / weekly-experiment 两作业新增「data_quality 前置(非阻断) → 实验任务 → monitor 后置(非阻断) → build 刷新(非阻断)」，生产冻结 SHA 守卫保持最高优先级、未削弱。
- ✅ Step 5 自动化：Daily/Weekly 链路注入完成；monitor/data_quality/build 均 `|| echo` 非阻断。
- ✅ Step 6 生产保护：monitor/main、data_quality/main 经测试验证不修改 7 个生产冻结文件（含 `dlt_history.json` 本身只读）。
- ✅ Step 7 测试 `tests/test_phase16_step6.py` **15 passed**（monitor 6 + data_quality 7 + 生产隔离 2）。
- ✅ Step 8 生产隔离复核：`PRODUCTION_ISOLATION = PASS`——7 个生产文件 mtime/SHA 与 STEP 1 baseline 逐字节一致；`structure_profile.json` 全量 SHA 匹配；`experiment_scheduler.py`/`experiment_store.py` 对 HEAD 无 diff。
- ✅ Step 9 报告 `reports/Phase16-Step6-Report.md`（13 节，含 FACT/EXPERIMENT/INTERPRETATION/LIMITATION）。
- ✅ Step 10 Git 提交（仅实验层文件，不触碰既有未提交生产修改、不 push）。

**测试结论**: 完整 pytest **337 passed / 1 failed**；唯一失败为历史既有 `test_phase14_step3.py::test_load_data`（硬编码期号 19132 vs 当前 19134），**PRE_EXISTING_FAILURE，无 NEW_REGRESSION**。

**已知问题**: `experiment_runs.sqlite` 仍 ABSENT（调度器尚未实际跑过）→ monitor 返回 unavailable（正常初始态）；真实 `dlt_history.json` 1000 期触发 degraded（年界大跳 19150→20001 等，已附注需人工确认，非采集故障）。

**纪律**: 未改 scorer/recommender/scheduler/publisher；未改 `adaptive_weights.yaml`；未改 `structure_profile.json`；未改 `experiment_store` 算法/结构；未改 `experiment_scheduler` daily/weekly/manual 行为；未把监控/质量结论接入生产推荐。

---

### Phase 16 Step 7: 实验调度器 CI 失败隔离加固 (P1 · 实验层 · 非生产 · 已完成)

**目标**: 修复 STEP 1 只读检查发现的 P1 缺口——`experiment_scheduler --daily/--weekly` 两 CI 步骤缺 `|| echo` 失败隔离；CI 默认 `set -e`，调度器一旦非零退出会中止后续生产 commit/deploy，违反"实验失败不阻断生产"原则。

**完成内容**:
- ✅ Step 1 只读检查：确认 P1（analyze 作业 203 行 / weekly-experiment 作业 311 行缺 `|| echo`）；同 job 内 data_quality/monitor/build 步骤均有隔离。
- ✅ 实施（ADD-ONLY）：两步骤末尾追加 `|| echo "experiment scheduler 失败（已隔离，不阻断生产）"`，与既有 data_quality/monitor/build 隔离策略一致。
- ✅ 本地验证：`yaml.safe_load` 语法通过；`data/structure_profile.json` SHA256 `ef678954…` 逐字节未变；`git show --stat` 确认仅 `.github/workflows/dlt-analysis.yml`（+4/-2）。
- ✅ Git 提交（仅 yml，不 push）：`7b3876f`（fix: Phase16 P1 实验调度器步骤加失败隔离）。
- ✅ 生产隔离：零改实验/生产逻辑；调度器 `--daily/--weekly/manual` 行为未变。

**已知缺口（P2，可选，本轮未做）**: 开奖日/周日多 cron 并发竞争 SQLite 与 git push；未来可加 `concurrency:` 组缓解，本轮未实施（避免影响既有 job 并发行为，且需用户确认）。

**部署状态**: 本地已提交，待推送后由 GitHub Actions 自动生效（当前工作区有 pre-existing 未提交改动 + 本地落后远程 `aff2d9c`，未擅自 push 以免带入脏数据 / 覆盖 CI 每日提交）。

**纪律**: 未改 scorer/recommender/scheduler/publisher；未改 `experiment_scheduler` 行为；未改 `structure_profile.json`；仅改 CI 配置文件。

---

## 当前未完成任务

### Phase 9-D: 统一推荐输出层设计

**任务**: 设计 `final_recommendation` 统一输出层

**状态**: 🟡 进行中 (暂停开发，保持现状)

**下一步**:
- 等待用户明确 v2.0 开发指令
- 不主动推进新阶段
- 保持现有稳定架构运行

---

## 注意事项

### 当前已知问题

1. **数据格式兼容**
   - 现状：`recommendations.json` 使用数组格式
   - 影响：首页展示正常
   - 风险：低

2. **CDN 缓存**
   - 缓存策略：`max-age=14400` (4 小时)
   - 影响：修改后需等待或清除缓存
   - 风险：中

### 禁止修改区域

- ❌ **算法层**: `src/` 目录推荐算法
- ❌ **数据生成层**: 推荐生成逻辑
- ❌ **产品逻辑**: 首页展示逻辑
- ❌ **UI 样式**: 现有页面样式

**原则**: 只读维护，不新功能开发

### 部署信息

| 项目 | 值 |
|-----|-----|
| **生产地址** | https://500wan.mootlsv.com/ |
| **CDN** | Cloudflare Pages |
| **GitHub** | https://github.com/zzz7491/dlt-assistant |
| **分支** | master |
| **最近部署** | R5.2 热修复（`wrangler pages deploy` → dlt-assistant master → 绑定 500wan.mootlsv.com；生产代码 = `8d33a15`） |

---

## 维护建议

1. **每日检查**: CDN 状态 + 数据加载
2. **每周备份**: 关键配置文件
3. **月度报告**: 运行状态总结
4. **异常处理**: 立即停止 → 诊断 → 修复

---

**最后更新**: 2026-08-22 22:01  
**维护人**: AI Assistant
