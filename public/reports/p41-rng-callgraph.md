# P4-1 RNG 调用链审计（只读）

基线 commit：`59da681b663bcd093952092a5a4e3bd56e5921b6`（tag `p3-research-closed-2026-10-01`）
审计时间：2026-10-02，仅只读，未修改任何代码。

## 1. C 候选生成器

- 函数：`src/recommender.py::_strategy_random(analysis, cfg, rng)`
  - `front = sorted(rng.sample(range(front_min, front_max+1), 5))`
  - `back  = sorted(rng.sample(range(back_min, back_max+1), 2))`
  - 纯 RNG 抽样，合法规则内。C 的输出**完全由传入的 `rng` 状态决定**。
- 调度器：`_STRATEGY_FUNCS = {"A":_strategy_balanced,"B":_strategy_hotcold,"C":_strategy_random,"D":_strategy_scored}`

## 2. C seed 参数来源（单点）

`src/recommender.py::recommend()`（第 230-246 行）：
```python
seed = cfg["recommend"].get("seed")      # 唯一 seed 入口
rng  = random.Random(seed)               # 单实例，被 A/B/C(/D) 顺序共享
out = {}
for key in ("A","B","C"):
    out[key] = [_STRATEGY_FUNCS[key](analysis, cfg, rng) for _ in range(per)]
if stats is not None:
    out["D"] = [_STRATEGY_FUNCS["D"](analysis, cfg, rng, stats) for _ in range(per)]
```
- 单一 `rng` 实例顺序驱动 A→B→C→D。
- `seed` 仅来自 `cfg["recommend"]["seed"]`，**没有任何其它注入点**。

## 3. seed=None 时实际发生什么

- `config/settings.yaml` → `recommend.seed: null`（生产默认）。
- `random.Random(None)`：CPython 从 `os.urandom` / 系统熵播种。
- 后果：**同一 process 内两次 `recommend()` 结果不同；跨 process 亦不同**。
- 影响面：A（`rng.sample/choice`）、B（`rng.sample/choice`）、C（`rng.sample`）全部非确定。
- D：正常路径不调 rng（仅当 `front_top/back_top` 为空时 fallback `rng.sample`），但共享同一 rng 实例，故其 fallback 亦依赖 A/B/C 消耗的 rng 状态。

## 4. 同一期重复执行是否可能不同

**是（缺陷确认前置判断）**。
- `scheduler.run_once` 每次运行调用一次 `recommend()`；重复运行（同一 publication context，即同一 latest draw → 同一 target_issue）会得到**不同的 A/B/C 号码**。
- `recommendations.save` 按 `(target_issue, strategy, idx)` 覆盖旧记录 → 未发布前每次重跑会用新随机值覆盖。

## 5. publication snapshot 是否首次生成后冻结

**是。**
- `src/publisher.py::upsert_published_snapshot`：
  - 该 issue 无快照 → 追加（created）；
  - 已有且 `snapshot_hash` 相同 → unchanged（幂等）；
  - 已有但内容不同 → **conflict，保留原快照，绝不覆盖**（不可变核心）。
- `snapshot_hash` 覆盖 issue/primary_strategy/front/back/reason/final_score/final_breakdown/model_version/explanation，**不含 published_at** → 同内容重放 hash 不变。
- 26112 当前快照 hash 复核 = `bea8ef87...ae5fad`（与基线一致，见 STEP 7）。
- **publisher 不重新生成 C 候选**：它只读取 `reports/recommendations.json` / `public/data/recommendations.json` 已生成的号码，做加法字段 + final_score + 冻结快照。因此快照冻结的是「首次生成时被选定的 primary 号码」。

## 6. 其它策略 / 模块的 nondeterministic RNG

- `src/recommender.py`：生产唯一非确定点（seed=None）。
- `src/experiment_scheduler.py::_ensure_random_baseline` → `random_baseline_runner.generate_random_tickets(n_bets, seed=123)`：固定 seed=123，确定；且为实验层，不写生产推荐。
- `src/experiment.py`：研究/演示层，固定 seed=42，非生产。
- `src/evaluation/*`：research only，使用显式/固定 seed（如 20260930、bootstrap_seed），不进生产调用链。
- `src/publisher.py` / `final_score.py` / `explanation.py` / `backtest.py` / `reflection.py` / `analyzer.py` / `reporter.py`：**无 RNG**（纯函数或规则映射）。publisher 仅 `published_at`/`updated_at` 为合法时间元数据，且已排除出 `snapshot_hash`。

## 7. 调用链汇总

```
生产调用链（每日 GitHub Actions cron）：
  .github/workflows/dlt-analysis.yml
    └─ python -m src.scheduler --once
         └─ scheduler.run_once
              ├─ scraper.run → analyze()          (确定性)
              ├─ recommend(analysis, cfg, stats)  ← RNG 唯一入口 (seed=None ⇒ 非确定)
              │     └─ random.Random(None) → A/B/C(/D fallback)
              ├─ recommendations.save(reports/recommendations.json)
              ├─ backtest / reflection            (确定性)
              └─ report (确定性)

发布调用链：
  python -m src.publisher --safe
    └─ publisher.publish
         ├─ build_recommendations (读已生成号码)
         ├─ final_score.compute_final_scores     (确定性纯函数)
         ├─ _build_primary_explanation           (确定性)
         ├─ upsert_published_snapshot           (不可变；conflict 保护)
         └─ build_review (读不可变快照)

API / manual：
  仓库无 FastAPI/Flask 等 HTTP 层（.agnes/work/gate3-bak-audit 内的 api_server.py 为历史备份，非当前生产）。
  手动触发 = scheduler --once / publisher，均走上述链。
```

## 8. 缺陷结论

- **C RNG 可复现性风险 = 确认**。生产 `recommend.seed: null` 使 C（及 A/B）候选每次生成不同。
- 修复面 = 单一入口 `cfg["recommend"]["seed"]` 的 seed=None 生产注入点（`scheduler.run_once`）。
- 快照不可变性已存在（publisher conflict 保护）；本 P4-1 仅让「首次生成」本身可复现，**不改写任何历史快照（含 26112）**。
