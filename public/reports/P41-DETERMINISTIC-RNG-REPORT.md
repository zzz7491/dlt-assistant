# P4-1 DETERMINISTIC RECOMMENDATION REPRODUCIBILITY GATE — 报告

基线 commit：`59da681b663bcd093952092a5a4e3bd56e5921b6`（tag `p3-research-closed-2026-10-01`）
范围：仅 P4-1（Production Hardening & Product Integrity 的 RNG 可复现性子任务）
本轮性质：CODE_GATE（不含部署）

## 0. 范围与禁令遵守

- 未做 feature mining / selector tuning / 调权追命中 / 挑"最好"seed / ML。
- 未改 `recent_issues=1000`、A/B/D 算法、selector 逻辑、26112 immutable snapshot。
- 修改仅 1 个 tracked 文件（`src/scheduler.py`）+ 1 个新增 stdlib helper（`src/deterministic_rng.py`）。
- seed 契约**不以命中率选择**（见 STEP 11）。

## 1. RNG DEFECT CONFIRMED: **YES**

生产 `config/settings.yaml` → `recommend.seed: null`。`src/recommender.py::recommend()`
第 238-239 行 `seed = cfg["recommend"].get("seed"); rng = random.Random(seed)`。
`random.Random(None)` 以 OS entropy 播种，故同一 publication context 重复生成
**A/B/C 每次不同**（D 正常路径 rng-free，但共享同一 rng 实例，其 fallback 亦受影响）。

复现证据（`reports/p41-rng-before.json`，seed=None，每 context 20 次）：
- 12/12 contexts 每个产生 20 个不同 C 候选（front/back 均不同）。
- `REPRODUCIBILITY_DEFECT_CONFIRMED = YES`。

## 2. ROOT CAUSE

单一 `rng = random.Random(cfg["recommend"]["seed"])` 入口；生产默认 `seed: null`
→ 非确定播种。调用链：`scheduler.run_once → recommend(analysis,cfg,stats)`
（`recommender.py:63`），seed 仅来自 `cfg["recommend"]["seed"]`，无其它注入点。

## 3. OLD PRODUCTION SEED BEHAVIOR

`recommend.seed = None` → `random.Random(None)` → 每次 process 运行 A/B/C 候选
不同；`recommendations.save` 按 `(target_issue,strategy,idx)` 覆盖 → 未发布前每次
重跑都用新随机值覆盖；publisher 再把「当时被选定的 primary」冻结成不可变快照
（conflict 保护）。即：**首次生成非确定**，但一旦发布快照即冻结。

## 4. NEW SEED CONTRACT

`seed = int.from_bytes(SHA256(f"{game_id}|{target_issue}|{strategy_id}|{algorithm_version}").digest()[:32], "big")`
- 常量：`game_id="DLT"`、`strategy_id="BUNDLE"`、`algorithm_version="dlt-recommender-v1"`。
- 仅生产路径 `seed=None` 处注入；显式 seed 原样透传（向后兼容）。
- 缺失任一 identity 分量 → `SeedDerivationError`（fail-closed，绝不回退 seed=None）。
- 详情：`docs/architecture/DETERMINISTIC-RNG-CONTRACT.md`、`reports/p41-seed-contract.json`。

## 5. SEED USES HIT PERFORMANCE: **NO**

seed 是「可复现命名空间键」，非性能选择键。未读取任何 hit/backtest/seed-0/20260930/percentile 作为 seed 选择依据。STEP 11 通过。

## 6. SAME CONTEXT REPEATABLE: **YES**

`reports/p41-rng-after.json`：
- 100 contexts × 10 repeats（A/B/C RNG 路径）：unique output = 1 → **100/100 PASS**。
- D 确定性抽查 12 contexts × 3 repeats：stable（D 主路径 rng-free）→ PASS。

## 7. CROSS PROCESS REPEATABLE: **YES**

20 contexts，独立子进程 process A == process B → **20/20 PASS**
（排除 Python hash/random state 掩盖）。

## 8. EXPLICIT SEED BACKWARD COMPATIBLE: **YES**

patch 仅改 `scheduler.py` 注入点；`recommender.py` 未改。显式 `C(seed=0)/C(seed=1)/C(seed=20260930)`
行为 patch 前后完全一致（test_11/12/13 + 注入逻辑验证：explicit seed 不被覆写）。

## 9. PUBLICATION SEMANTIC IDEMPOTENT: **YES**

`snapshot_hash` 覆盖 issue/primary_strategy/front/back/reason/final_score/final_breakdown/
model_version/explanation，**排除 published_at**；同 semantic payload + 不同时间戳 → 同 hash（test_23）。
`upsert_published_snapshot` 幂等：created → unchanged；不同 payload 同 issue → conflict（不可变保护，test_24）。
合法发布 timestamp 未被破坏。

## 10. CONCURRENT GENERATION CONSISTENT: **YES**

同一 target 两个并发 generation attempt 的 A/B/C semantic payload 一致（test_25，ThreadPool 双 worker）。
现有幂等保护（snapshot conflict）已验证，未重构。

## 11. SEED COLLISIONS: **0**

1000 synthetic publication identities → unique seeds = 1000，collisions = 0（STEP 10 sanity，非密码学安全声明）。

## 12. 完整性矩阵（STEP 17 required answers）

| 项 | 结论 |
|----|------|
| RNG DEFECT CONFIRMED | **YES** |
| ROOT CAUSE | 单 `rng=random.Random(None)` 入口 + 生产 `seed:null` |
| OLD PRODUCTION SEED BEHAVIOR | 首次生成非确定；发布后快照冻结 |
| NEW SEED CONTRACT | SHA-256(game_id\|target_issue\|strategy_id\|algorithm_version) → 256-bit int |
| SEED USES HIT PERFORMANCE | **NO** |
| SAME CONTEXT REPEATABLE | **YES** (100/100) |
| CROSS PROCESS REPEATABLE | **YES** (20/20) |
| EXPLICIT SEED BACKWARD COMPATIBLE | **YES** |
| PUBLICATION SEMANTIC IDEMPOTENT | **YES** |
| CONCURRENT GENERATION CONSISTENT | **YES** |
| SEED COLLISIONS | **0** |
| A CHANGED | **NO** |
| B CHANGED | **NO** |
| D CHANGED | **NO**（算法未改，主路径 rng-free） |
| SELECTOR CHANGED | **NO** |
| WEIGHTS CHANGED | **NO** |
| 1000 CAP CHANGED | **NO** |
| 26112 SNAPSHOT CHANGED | **NO**（hash `bea8ef87f3f137238686ae52712f922956215408f0cf54187b9295d8f1ae5fad` 复核不变，test_22） |
| UI CHANGED | **NO** |
| ML ADDED | **NO** |

## 13. 测试结果

`tests/test_p41_deterministic_rng.py`：28 tests / **41 assertions**（≥30）全部 PASS
（`.venv` Python 3.14，stdlib unittest，无第三方依赖）。覆盖：same identity、
issue/version/strategy/game namespace、explicit-seed 兼容、100-context 同进程、
D 确定性、cross-process 20、collision 1000、无 time/pid/machine/hash 依赖、
fail-closed、publication 语义幂等、26112 immutable、1000 cap 不变、仅允许 scheduler 修改。

## 14. 变更文件（STEP 16 审计）

- tracked 修改：**仅** `src/scheduler.py`（STEP 6 最小 patch）。
- 新增 source：`src/deterministic_rng.py`（stdlib helper）。
- 新增 research 工件（untracked）：`docs/architecture/DETERMINISTIC-RNG-CONTRACT.md`、
  `reports/p41-*.{json,md}`、`scripts/p41_*.py`、`tests/test_p41_deterministic_rng.py`。
- **无** experiment.html / 预测文案 / UI / CSS / P4-2 内容 / 其它无关修改。

## 15. RELEASE DECISION（STEP 18）

- `P41_CODE_GATE = PASS`（所有测试 PASS，缺陷确认，兼容性/幂等/并发/失败行为均通过）。
- `PRODUCTION_DEPLOY_AUTHORIZED = NO`（本轮不 deploy、不 push）。

## 16. 产物清单

- `reports/p41-rng-callgraph.md`（STEP 2）
- `reports/p41-rng-before.json`（STEP 3）
- `docs/architecture/DETERMINISTIC-RNG-CONTRACT.md` + `reports/p41-seed-contract.json`（STEP 4/5）
- `src/deterministic_rng.py` + `src/scheduler.py`（STEP 6）
- `reports/p41-rng-after.json`（STEP 9/10）
- `tests/test_p41_deterministic_rng.py`（STEP 15）
- `reports/p41-production-diff.json`（STEP 16）
- 本报告（STEP 17）
