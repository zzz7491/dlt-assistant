# Phase 16 Step 6 报告 · 实验运行状态监控 + 数据质量护栏

> 阶段定位：在**完全不改变现有生产推荐与实验算法**的前提下，补齐两个可观测性缺口：
> 「实验是否真的自动运行了？」与「实验使用的数据是否可靠？」
> 全部为 **ADD-ONLY / EXPERIMENT-ONLY**，与既有生产链路、既有实验算法、Step 5 调度器行为零冲突。

---

## 1. 目标

- 为实验自动化提供**运行状态可观测性**（Daily/Weekly/Manual 是否运行、成功/失败、最近错误、覆盖期数）。
- 为实验输入数据 `data/dlt_history.json` 提供**完整性护栏**（重复/缺口/非单调/字段异常/空数据）。
- 两类新能力必须**失败隔离**：自身异常只能产出结构化 `unavailable/error` 状态，绝不导致生产推荐失败。
- 任何结果都**不参与生产推荐决策**，不自动调权，不修改生产推荐。

## 2. 背景

- Phase 15/16 已证明：模型统计区分度有限、coverage_boost 不稳定、random 是重要锚点；实验层不得包装成预测能力。
- Phase 16 Step 5 已建成「自动运行 + 增量 + 失败隔离 + 生产冻结」闭环（experiment_scheduler + experiments.sqlite + experiment_runs.sqlite + build + CI 守卫）。
- **缺口 A（运行状态监控）**：`experiment_runs.sqlite` 此前从未被实际生成，experiment.html 无「运行健康」视图——无法验证自动运行是否真的发生。
- **缺口 B（数据质量护栏）**：实验全部读取 `data/dlt_history.json`；若该文件出现期号缺口/重复/非单调/字段异常，实验会静默产出误导结果。

## 3. 只读检查（STEP 1 结论）

- **生产冻结基线门通过**：`data/structure_profile.json` canonical SHA256 = `ef67895429f4d742a88b21767701073df7cb51cd767f7281abaac7a476207cac`，与要求基线逐字节一致，未触发 PRODUCTION BASELINE MISMATCH 停止条件。
- 其余生产文件（scorer/recommender/scheduler/publisher/recommendations 三处/`data/recommendations.json` ABSENT）状态已记录为 STEP 1 baseline，本阶段结束逐文件复核一致。
- `experiment_runs.sqlite` 当时 ABSENT（调度器尚未实际运行 → 运行监控数据从未产生），本阶段即补齐该可观测性。
- 完整测试基线：**322 passed / 1 failed**（既有 `test_phase14_step3::test_load_data`）。

## 4. 设计

- **系统结构（不变）**：生产 = 开奖→scheduler→分析→推荐→publisher→recommendations(冻结)；实验 = 开奖→experiment_scheduler→experiments.sqlite→evaluators→reports/*.json→build→public/data→experiment.html。两条链路逻辑隔离。
- **新增实验层**：
  - `src/experiment_monitor.py`：只读 `data/experiment_runs.sqlite`（run_log + meta 表，schema 与 `experiment_scheduler._connect_run_db` 严格一致：id/mode/task/started_at/ended_at/duration_s/status/error/output_files/coverage_periods + meta(key,value)），聚合输出 `reports/experiment_run_status.json`。**不 import/调用任何生产模块，不写生产文件，不修改 experiments.sqlite / experiment_runs.sqlite**。
  - `src/experiment_data_quality.py`：只读 `data/dlt_history.json`，输出 `reports/experiment_data_quality.json`。9 项检查（JSON 可解析/顶层结构/issue 存在/重复/单调/缺口/字段缺失异常/空/最新期识别）。
  - `public/data/experiment_run_status.json` + `experiment_data_quality.json`（由 build 脚本派生）。
  - `experiment.html` 新增 `#sec-health` 区块；`experiment.js` 新增 `renderHealth()` + `loadHealth()`（非阻断，失败仅本区块 unavailable）。
  - `dlt-analysis.yml` 在 analyze / weekly-experiment 两作业新增「数据质量前置（非阻断）→ 实验任务 → 监控（非阻断）→ 刷新展示（非阻断）」，生产冻结 SHA 守卫保持最高优先级、未削弱。
- **为何不影响生产**：两模块仅读实验输入/运行记录，仅写 `reports/experiment_*.json` + `public/data/experiment_*.json`；完全不触及 scorer/recommender/scheduler(生产)/publisher、recommendations.json、adaptive_weights.yaml、structure_profile.json。

## 5. 实现

- `experiment_monitor.build_status()`：处理 4 类异常——库不存在→`unavailable`；库为空→`unavailable`；库损坏（DatabaseError）→`error`；任意意外→`error`。聚合 total_runs / 各模式最近状态与次数 / 各任务 success+failed / last_failed_task / last_error / coverage_periods / overall_status(HEALTHY|DEGRADED)。
- `experiment_data_quality.build_quality()`：9 项检查输出 `status` ∈ {ok, degraded, error}。`error` 仅用于 JSON 不可解析或顶层结构异常；`degraded` 用于重复/缺口/非单调/字段缺失异常/空；`ok` 为全通过。
- **期号缺口处理（按实际规则，不猜测）**：大乐透 issue 为 `YYNNN` 格式（年+序号），年份边界天然存在大跳（实测 19150→20001 差 851 等）。因此「相邻 diff>1」**仅作为完整性提醒**并标 `degraded` + 附注「需人工确认，春节加开期不必然表示缺失」，**绝不臆断为数据缺失**。
- `scripts/build_experiment_display_data.py`：ADD-ONLY 新增两步 `build_if_present("experiment_run_status.json", ...)` 与 `build_if_present("experiment_data_quality.json", ...)`，沿用既有 `unavailable` 容错（源缺失/转换异常隔离）。
- CI：Daily/Weekly 均新增 data_quality 前置、monitor 后置、build 刷新，全部 `|| echo` 非阻断；生产冻结 guard 前后快照 diff 保持不变且为阻塞级。

## 6. 自动化

- **Daily**（随 analyze 作业 02:00 UTC / 开奖日 13:45 UTC 自动）：data_quality 前置 → experiment_scheduler --daily（增量追加+轻量报告+build）→ monitor 后置 → build 刷新 → 生产冻结守卫 → commit/deploy。
- **Weekly**（周日 04:00 UTC 自动 / dispatch=weekly）：data_quality 前置 → experiment_scheduler --weekly（全量 walk-forward 重回放，90min timeout）→ monitor 后置 → build 刷新 → 生产冻结守卫 → commit/deploy。
- **Manual**：experiment_monitor / experiment_data_quality 亦可独立手动运行查看状态；不从 manual 自动晋升到生产。
- 失败隔离：data_quality / monitor / build 任一步失败仅写 degraded/error 报告并 `|| echo`，**绝不阻断生产提交**；生产冻结 SHA guard 始终最高优先级。

## 7. 测试

- 新增 `tests/test_phase16_step6.py`：**15 项全部通过**（覆盖要求 ≥12 项并额外增加缺失字段/字段异常两项）。
  - monitor：正常运行 / 空库 / 库不存在 / 单任务失败 / 多任务失败 / 损坏库不崩（共 6）。
  - data_quality：正常(ok) / 重复期(degraded) / 期号缺口(degraded) / 非单调(degraded) / JSON 损坏(error) / 缺失字段(degraded) / 字段异常(degraded)（共 7）。
  - 生产隔离：monitor 不修改生产 / data_quality 不修改生产（含不改写 dlt_history.json 本身）（共 2）。
- 运行结果：**Step 6 专项 15 passed**；**Step 5 专项 14 passed**；**完整 pytest 337 passed / 1 failed**。

## 8. 生产隔离（PRODUCTION_ISOLATION = PASS）

| 文件 | baseline mtime | 当前 mtime | baseline SHA(前8) | 当前 SHA(前8) | 一致 |
|------|------|------|------|------|------|
| src/scorer.py | 1787392208 | 1787392208 | 2b5ee327 | 2b5ee327 | ✅ |
| src/recommender.py | 1787733209 | 1787733209 | 099aa520 | 099aa520 | ✅（既有未提交改动维持原样，mtime 未变） |
| src/scheduler.py | 1787733140 | 1787733140 | 15c447e7 | 15c447e7 | ✅（同上） |
| src/publisher.py | 1787420380 | 1787420380 | b09db087 | b09db087 | ✅ |
| data/structure_profile.json | 1787878602 | 1787878602 | ef678954 | ef678954 | ✅ |
| public/data/recommendations.json | 1787417025 | 1787417025 | 3426af13 | 3426af13 | ✅ |
| reports/recommendations.json | 1787836886 | 1787836886 | 5508af67 | 5508af67 | ✅ |
| data/recommendations.json | ABSENT | ABSENT | — | — | ✅ |

- canonical `structure_profile.json` 全量 SHA256：`ef67895429f4d742a88b21767701073df7cb51cd767f7281abaac7a476207cac` **MATCH ✅**。
- `src/experiment_scheduler.py`、`src/experiment_store.py`：`git diff` 对 HEAD 为空（本阶段未改动既有实验逻辑/算法）。
- 既有未提交生产改动（recommender/scheduler/reports/recommendations）mtime 与 STEP 1 baseline 逐字节一致，**本阶段未新增任何修改**。

## 9. 已知问题

- `experiment_runs.sqlite` 当前仍 ABSENT（调度器在 CI/本地尚未实际跑过一次）。monitor 对此返回 `unavailable` 并明确说明「正常初始状态」，不误报错误。首次实验日/周运行后该库将生成，监控才有数据。
- 真实 `data/dlt_history.json`（1000 期）触发 `degraded`：检测到年份边界大跳（19150→20001 等）。这是大乐透 `YYNNN` 编号的正常年界，已在报告中附注「需人工确认，非数据缺失」；属设计预期，非采集故障。

## 10. PRE_EXISTING_FAILURE

- `tests/test_phase14_step3.py::test_load_data`：硬编码 `assert issues[0]["issue"] == "19132"`，当前最新期为 `19134`。历史既有失败，与 Phase 16 Step 5/6 无关。**未修改该历史测试**（除非另行授权）。

## 11. NEW_REGRESSION

- **无（NEW_REGRESSION = none）**。完整 pytest 337 passed / 1 failed，唯一失败为上述 PRE_EXISTING_FAILURE。

## 12. 结论

Phase 16 Step 6 在零改生产、零改既有实验算法的前提下，补齐了实验自动化的两类可观测性：
- 运行状态监控（monitor）让「实验是否真的自动运行了」可被前端与 CI 检查；
- 数据质量护栏（data_quality）让「实验使用的数据是否可靠」可被持续校验，且对大乐透年界缺口如实标注「需人工确认」而非臆断。
两者均失败隔离、均不参与生产推荐决策。

## 13. 下一步

- 观察 1~2 个开奖日 + 首个周日：确认 CI 中 data_quality→experiment_scheduler→monitor→build 链路真实运行，`experiment_runs.sqlite` 生成后 monitor 出现 HEALTHY/DEGRADED 数据。
- 若 `data_quality` 持续 `degraded` 且人工确认属年界而非真实缺失，可考虑在报告中将「年界缺口」单独归类为 `ok(known_boundary)`，避免噪声；此项需先确认需求，不擅自扩大范围。
- 不自动进入 Phase 16 Step 7，等待下一步指令。

---

### FACT / EXPERIMENT / INTERPRETATION / LIMITATION 区分

- **FACT**：monitor 只读 run_log/meta；data_quality 实测真实 `dlt_history.json` 1000 期、latest=26097、monotonic=true、detected year-boundary gaps（19150→20001 等）。
- **EXPERIMENT**：本阶段为监控/护栏实验层工具，本身不产生彩票预测结论。
- **INTERPRETATION**：年界缺口属 `YYNNN` 编号正常年切换，标记 degraded 仅为完整性提醒，须人工确认。
- **LIMITATION**：monitor 在 `experiment_runs.sqlite` 生成前只能给出 unavailable（无法确定自动化是否执行过）；data_quality 仅校验输入完整性，不保证开奖号码「真实性/正确性」。
