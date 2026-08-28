# Phase 16 Step 5 报告 · 实验数据自动更新流水线

> 目标：在「绝不修改生产逻辑 / 绝不修改生产推荐 / 生产冻结」的前提下，
> 让实验系统随每日开奖**自动运行 + 自动更新 + 增量计算 + 失败隔离 + 结果展示**，
> 生产推荐保持冻结。

- 日期：2026-08-28
- 范围：纯实验层（新增模块 / 脚本 / 测试 / CI；不改动 scorer / recommender / scheduler / publisher / 生产 recommendations）

---

## 1. 概述与目标

Phase 16 Step 4 已建立「诚实、透明、可追溯」的实验展示层（公开页面只读 `reports/*.json` → `public/data/*.json`）。
但当时实验层**零自动化**：每一次更新都需人工跑脚本，且无法随开奖增量追加、无法失败隔离、无生产冻结守卫。

Step 5 补上自动化与工程化闭环：

| 能力 | 实现 |
|------|------|
| 自动运行 | `src/experiment_scheduler.py`（`--daily` / `--weekly` / `--manual`） |
| 自动更新 | 日任务随开奖追加实验库 + 重算轻量报告 + 生成展示 JSON |
| 增量计算 | `last_processed_issue` 位点 + `experiment_store` 幂等（`INSERT OR IGNORE` + 评估跳过已评估行） |
| 失败隔离 | 每个实验任务独立 `try/except`，单任务失败不影响其它任务与生产 |
| 结果展示 | `scripts/build_experiment_display_data.py` 容错（缺失报告 → `status=unavailable`） |
| 生产冻结 | CI 守卫：实验前后比对生产冻结文件 SHA，任一变更即阻断提交 |

---

## 2. 硬约束遵守情况

### 2.1 绝对禁止（均未违反 ✅）

| 禁止项 | 检查结论 |
|--------|----------|
| 修改 scorer.py / recommender.py / scheduler.py / publisher.py | 4 个生产文件 mtime 与 Step 4 基线**完全一致**（见第 10 节） |
| 修改生产 recommendations.json 生成规则 | 未触碰；`data/recommendations.json` 仍 ABSENT，生产推荐仅由 `src.scheduler --once` + publisher 维护 |
| 自动调整生产评分权重 | 实验调度器**绝不**写 `config/adaptive_weights.yaml`；手动模式也只产出 `RECOMMENDATION_FOR_REVIEW.json`（binding=false） |
| 用实验结果覆盖生产推荐 | 实验层只写 `data/experiments.sqlite` / `reports/*.json` / `public/data/*.json`（实验展示），不回写生产 |
| 为通过测试修改无关生产逻辑 | 未改动任何生产模块 |
| 删除既有函数 / 无必要重构稳定代码 | 仅新增模块与脚本，未删改既有函数 |

### 2.2 允许项（已使用）

新增模块 `src/experiment_scheduler.py`、`tests/test_phase16_step5.py`；
修改脚本 `scripts/build_experiment_display_data.py`（容错，不改其数据来源）；
修改 CI `.github/workflows/dlt-analysis.yml`（注入实验步骤 + 守卫，不冲突既有流程）；
新增实验运行记录库 `data/experiment_runs.sqlite`（与 `experiments.sqlite` 分离，不污染实验数据）。

---

## 3. 新增 / 修改文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/experiment_scheduler.py` | 新增 | 三层调度器（daily/weekly/manual）+ 失败隔离 + 运行记录 |
| `scripts/build_experiment_display_data.py` | 修改 | 改为容错：源报告缺失 → 写 `status=unavailable`；单文件异常隔离 |
| `.github/workflows/dlt-analysis.yml` | 修改 | 注入日实验步骤 + 生产冻结守卫；新增周日 cron + dispatch 输入 + `weekly-experiment` 作业 |
| `tests/test_phase16_step5.py` | 新增 | 14 项测试，覆盖增量 / 幂等 / 失败隔离 / 守卫 / 周任务 |
| `data/experiment_runs.sqlite` | 新增（运行期） | 调度器运行记录（run_log + meta），与实验数据分离 |

> 注：`dlt-analysis.yml` 提交范围原本已覆盖 `data reports public`，实验数据随之自动提交，无需新增冲突工作流。

---

## 4. 三层自动化设计

```
┌─────────────────────┐   开奖后(每日 02:00 / 13:45 UTC)   ┌──────────────────────────┐
│  dlt-analysis.yml    │ ───────────────────────────────▶ │ analyze 作业:            │
│  (schedule)          │                                    │  scheduler --once       │
│                      │                                    │  → 实验层守卫(前)        │
│                      │                                    │  → experiment --daily    │
│                      │                                    │  → 实验层守卫(后)        │
│                      │                                    │  → git commit + deploy   │
└─────────────────────┘                                    └──────────────────────────┘
        │ 周日 04:00 UTC
        ▼
┌──────────────────────────┐
│ weekly-experiment 作业:   │  全量 walk-forward 重回放（~数十分钟）
│  scheduler --once         │  history / random / constrained / feature_ablation /
│  → 实验层守卫(前)          │  strategy_removal / ensemble / 反事实聚合
│  → experiment --weekly    │  → 实验层守卫(后) → commit + deploy
│  → 实验层守卫(后)          │
└──────────────────────────┘

manual（本地 / dispatch=weekly 时可选）：
  python -m src.experiment_scheduler --manual
  → 仅生成 reports/RECOMMENDATION_FOR_REVIEW.json（binding=false，供人工审阅）
```

- **daily**：增量追加实验库（评估新开奖期 + 预测目标期含 random 基线）+ 重算轻量报告（ranking / entertainment / diagnostics / feature_gain）+ 生成展示 JSON。秒级~分钟级。
- **weekly**：周期重回放 / 重验证（walk-forward 900 期），数十分钟级。独立作业，超时 90 分钟。
- **manual**：本地人工审阅任务，仅产出建议文件，绝不改生产、绝不自动调权、绝不替换推荐。

---

## 5. 增量机制（Step 4 落地）

- 位点：`meta(last_processed_issue)` 记录已处理的最新开奖期。
- 日任务启动即比对历史 `data/dlt_history.json` 与位点：
  - 无新开奖期且目标期已全模型保存 → 返回 `NO_NEW_DATA`（不重算、不预测）。
  - 有新期 → 仅对 `issue > last_processed_issue` 的期做评估（增量，不回评）。
- 幂等复用：`experiment_store.save_experiment` 使用 `INSERT OR IGNORE` + `UNIQUE(issue, model_version)`；`evaluate_draw_result` 跳过已评估行。重复运行不产生重复数据。
- 异常场景处理（均不影响生产）：
  - **NO_NEW_DATA**：直接返回，零副作用。
  - **issue 缺失 / 重复**：仅处理位点之后的期；重复期评估被幂等跳过。
  - **issue 倒退**（历史回退）：打印告警，**不向后推进** `last_processed_issue` 标记（已修复 `run_daily` 的 meta 更新条件）。
  - **开奖数据损坏 / recommendations 缺失 / SQLite 锁 / 模型缺失 / random 缺失**：各任务独立 `try/except` 隔离，单点失败不影响其它任务与生产推荐。

---

## 6. 失败隔离状态机（Step 7）

| 状态 | 触发 |
|------|------|
| `SUCCESS` | 所有任务成功 |
| `PARTIAL_SUCCESS` | 至少一个任务失败，但非全部失败 |
| `NO_NEW_DATA` | 无新开奖数据，无需更新 |
| `FAILED` | 全部任务失败 |
| `BLOCKED_PRODUCTION_CHANGE` | 由 CI 守卫强制判定（实验意外改动生产冻结文件 → 阻断提交），不在此模块内 |

- 退出码：CI 视角下 `NO_NEW_DATA / SUCCESS / PARTIAL_SUCCESS` 均视为成功（退出 0），仅 `FAILED` 退出 1；
  保证「单实验失败」不会阻断生产每日提交。
- 调度器顶层 `try/except` 兜底：调度器自身异常也被捕获并记录，绝不冒泡为生产失败（退出 1）。

---

## 7. CI 生产冻结守卫

在 `analyze` 与 `weekly-experiment` 两个作业中，实验步骤前后各计算一次生产冻结文件 SHA：

```
守卫文件集：
  src/scorer.py  src/recommender.py  src/scheduler.py  src/publisher.py
  data/structure_profile.json
  public/data/recommendations.json  reports/recommendations.json  data/recommendations.json
```

- 实验步骤**前**快照 → 实验步骤**后**快照；`diff` 不一致 → `exit 1` 阻断后续 `git commit`，保护生产不被污染。
- 关键修正：`run_pipeline` 调用 `generate_structure_profile(train)` 时其 `output_path` 默认值为**临时 scratch 文件**（非 canonical `data/structure_profile.json`），因此实验日任务**不会**改写 canonical 结构画像；守卫对 `structure_profile.json` 的 SHA 校验在自动化中**不会误触发**。

---

## 8. 测试覆盖（14 项，全部通过 ✅）

| # | 测试 | 验证点 |
|---|------|--------|
| 1 | test_no_new_data | 已追平 → `NO_NEW_DATA`，不触发预测管道 |
| 2 | test_incremental_evaluates_only_new | 增量仅评估新期，不回评已处理期 |
| 3 | test_evaluate_draw_result_idempotent | 同期限评估幂等，无重复评估行 |
| 4 | test_issue_regression_keeps_marker | 历史倒退不向后推进位点 |
| 5 | test_single_task_failure_isolated | 单任务失败隔离 + 整体状态聚合 |
| 6 | test_prod_change_guard_blocks | 生产文件变更 → 守卫判定 BLOCKED |
| 7 | test_canonical_structure_profile_untouched_and_guard | `run_pipeline` 不写 canonical 画像 + 守卫判定 |
| 8 | test_display_missing_report_fallback | 报告缺失 → `status=unavailable`（不死） |
| 9 | test_save_experiment_sqlite_idempotent | `save_experiment` 同 (issue,model) 幂等 |
| 10 | test_daily_no_full_backfill | 日任务不触发 walk-forward 全量重回放 |
| 11 | test_weekly_runs_specified_modules | 周任务触发 6 个指定重度子任务 |
| 12 | test_manual_review_only | 手动任务仅产出审阅建议，不碰生产推荐 |
| 13 | test_random_missing_no_prod_failure | random 基线缺失不导致生产失败 |
| 14 | test_scheduler_self_failure_exits_nonzero | 调度器自身异常被兜底，退出非 0 |

运行：`python -m pytest tests/test_phase16_step5.py -q` → **14 passed**。

---

## 9. 性能评估

- **日任务（daily）**：`run_pipeline`（预测目标期，约数千候选打分）+ 轻量报告（读 `experiments.sqlite`，无重预测）+ 展示生成（文件复制/裁剪）。实测测试环境与 Phase 15 数据规模下为**分钟级**，远低于 `analyze` 作业 15 分钟超时。
- **周任务（weekly）**：walk-forward 全量重回放 ~900 期（Phase 15 实测约 65 分钟），独立 `weekly-experiment` 作业超时设为 **90 分钟**，容纳余量。
- 增量保证了日任务**不重放历史**，仅追加新期，性能恒定。

---

## 10. 生产隔离验证（Step 10）

与 Phase 16 Step 4 记录的基线逐字节比对：

| 文件 | 维度 | 基线 | 当前 | 结论 |
|------|------|------|------|------|
| src/scorer.py | mtime | 1787392208 | 1787392208 | ✅ 未变 |
| src/recommender.py | mtime | 1787733209 | 1787733209 | ✅ 未变 |
| src/scheduler.py | mtime | 1787733140 | 1787733140 | ✅ 未变 |
| src/publisher.py | mtime | 1787420380 | 1787420380 | ✅ 未变 |
| data/structure_profile.json | SHA256 | ef67895429f4d742a88b21767701073df7cb51cd767f7281abaac7a476207cac | 相同 | ✅ 未变 |
| data/recommendations.json | 存在性 | ABSENT | ABSENT | ✅ 未变 |

**结论：生产冻结文件全部未变更。**

---

## 11. 已知限制 / 不能做的事

- 实验系统**不预测彩票结果**，所有展示均标注「娱乐分析，非预测」；实验结论（含 random 基线对照）**不作为**任何中奖率/胜率证据。
- 周任务重度计算仍在 CI 内串行执行；若周日 04:00 与当日 `analyze` 提交并发，存在极小概率的 push 竞争（已用 `git pull --rebase` 兜底，不影响最终一致性）。
- 手动模式仅产出建议文件，任何权重/策略变更仍需人工确认后显式实施。
- `data/experiments.sqlite` 随每日提交增长；建议后续定期归档历史（不在本步范围）。

---

## 12. 后续建议

1. 合并后观察 1~2 个开奖日，确认 `analyze` 作业中的 `experiment --daily` 与守卫在真实 CI 中稳定运行（首次运行会触发全量 `experiments.sqlite` 初始化）。
2. 首次周日后检查 `weekly-experiment` 作业是否成功写回 `counterfactual_analysis.json` 等重度报告。
3. 若需更低 CI 负载，可将周任务迁移至独立低频 cron 或按需 `workflow_dispatch`（`experiment_mode=weekly` 已支持）。
4. 长期：为 `experiments.sqlite` 增加归档/裁剪策略，避免仓库无限增长。

---

### 附：执行纪律复核

- ✅ 仅新增/修改实验层与 CI，未触碰生产 `scorer/recommender/scheduler/publisher`。
- ✅ 未修改生产 `recommendations.json` 生成规则，未写 `adaptive_weights.yaml`。
- ✅ 未将实验结果包装为胜率证据；页面与报告持续标注「娱乐分析，非预测」。
- ✅ 全部变更为增量/加法，未删除既有函数、未无必要重构。
