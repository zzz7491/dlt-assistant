# -*- coding: utf-8 -*-
"""Phase 16 Step 5 · 实验自动化流水线测试套件（14 项）。

覆盖：
  1. NO_NEW_DATA          : 已追平则日任务返回 NO_NEW_DATA
  2. incremental          : 增量仅评估新开奖期，不回评已处理期
  3. evaluate idempotent   : 同一期重复评估不产生重复评估行
  4. issue regression     : 历史倒退时不向后推进 last_processed 标记
  5. single-task fail      : 单任务失败被隔离，不影响其它任务
  6. prod-file change     : 生产冻结文件变更时守卫判定为 BLOCKED
  7. canonical SHA change : structure_profile.json 不被实验污染 + 守卫判定
  8. display missing      : 报告缺失→生成 status=unavailable（不死）
  9. sqlite dup idempotent : save_experiment 同 (issue,model) 幂等
  10. daily no backfill    : 日任务不触发 walk-forward 全量重回放
  11. weekly specified     : 周任务触发指定的重度子任务
  12. manual review-only   : 手动任务仅产出审阅建议，不碰生产推荐
  13. random missing       : random 基线缺失不导致生产失败
  14. scheduler self-fail  : 调度器自身异常被兜底，退出非 0，不污染生产

所有测试均为沙箱（临时目录 / monkeypatch），不修改仓库生产文件。
"""
import json
import os
import sys
import tempfile
from unittest import mock

import pytest

import src.experiment_scheduler as es
from src import experiment_store as store


# ============================================================
# 守卫辅助（镜像 CI bash 守卫逻辑，供单测判定 BLOCKED）
# ============================================================

PROD_FROZEN = [
    "src/scorer.py",
    "src/recommender.py",
    "src/scheduler.py",
    "src/publisher.py",
    "data/structure_profile.json",
    "public/data/recommendations.json",
    "reports/recommendations.json",
    "data/recommendations.json",
]


def prod_guard_blocked(pre: dict, post: dict) -> bool:
    """若任一生产冻结文件的前/后快照（hash 或 ABSENT）不一致 → 应 BLOCK。"""
    for f in PROD_FROZEN:
        if pre.get(f) != post.get(f):
            return True
    return False


# ============================================================
# 通用沙箱夹具
# ============================================================

@pytest.fixture
def sandbox(monkeypatch):
    """将实验调度器的输出根重定向到临时目录，确保不污染真实仓库。"""
    tmp = tempfile.mkdtemp(prefix="dlt_exp_test_")
    data_dir = os.path.join(tmp, "data")
    reports_dir = os.path.join(tmp, "reports")
    public_data = os.path.join(tmp, "public", "data")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(public_data, exist_ok=True)
    monkeypatch.setattr(es, "ROOT", tmp)
    monkeypatch.setattr(es, "RUN_DB", os.path.join(data_dir, "experiment_runs.sqlite"))
    monkeypatch.setattr(es, "HISTORY_PATH", os.path.join(data_dir, "dlt_history.json"))
    return tmp


def _stub_pipeline(monkeypatch):
    """将 run_pipeline（重度预测）替换为无副作用桩，避免测试中的重计算。"""
    monkeypatch.setattr(
        "src.daily_prediction_pipeline.run_pipeline",
        lambda *a, **k: {"status": "ok"},
    )


def _isolate_daily(monkeypatch, history, last_processed, target_saved):
    """统一隔离 run_daily 的重度依赖，仅保留增量判定与失败隔离逻辑。"""
    monkeypatch.setattr(es, "_load_history", lambda: history)
    monkeypatch.setattr(es, "_get_meta", lambda k: last_processed if k == "last_processed_issue" else None)
    monkeypatch.setattr(es, "_target_fully_saved", lambda issue: target_saved)
    monkeypatch.setattr(es, "_ensure_random_baseline", lambda *a, **k: None)
    monkeypatch.setattr(es, "_daily_reports", lambda: [])
    monkeypatch.setattr(es, "_build_display", lambda: [])
    monkeypatch.setattr(es, "query_history", lambda *a, **k: [])
    _stub_pipeline(monkeypatch)


# ============================================================
# 1. NO_NEW_DATA
# ============================================================

def test_no_new_data(monkeypatch, sandbox):
    calls = []
    monkeypatch.setattr("src.daily_prediction_pipeline.run_pipeline",
                        lambda *a, **k: calls.append(1))
    _isolate_daily(monkeypatch, [{"issue": 100, "front": [1,2,3,4,5], "back": [1,2], "date": "x"}],
                   last_processed="100", target_saved=True)
    status = es.run_daily()
    assert status == es.STATUS_NO_NEW
    assert calls == []  # 无新数据不应触发预测管道


# ============================================================
# 2. incremental：仅评估新开奖期
# ============================================================

def test_incremental_evaluates_only_new(monkeypatch, sandbox):
    evaluated = []
    monkeypatch.setattr(es, "evaluate_draw_result",
                        lambda issue, actual: evaluated.append(issue))
    _isolate_daily(monkeypatch,
                   [{"issue": 99, "front": [], "back": [], "date": ""},
                    {"issue": 100, "front": [], "back": [], "date": ""}],
                   last_processed="99", target_saved=False)
    status = es.run_daily()
    # 仅新期 100 应被评估；99（≤ last_processed）不应回评
    assert "100" in evaluated
    assert "99" not in evaluated
    assert status in (es.STATUS_SUCCESS, es.STATUS_PARTIAL, es.STATUS_NO_NEW)


# ============================================================
# 3. evaluate_draw_result 幂等（同一期重复评估不产生重复评估行）
# ============================================================

def test_evaluate_draw_result_idempotent(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="dlt_store_")
    db = os.path.join(tmp, "experiments.sqlite")
    actual = {"front": [1, 2, 3, 4, 5], "back": [6, 7], "date": "2026-01-01"}
    store.save_experiment("12345", "v1", parameters={},
                          recommendations=[actual], db_path=db)
    store.evaluate_draw_result("12345", actual, db_path=db)
    store.evaluate_draw_result("12345", actual, db_path=db)  # 二次应被跳过
    rows = store.query_history(issue="12345", only_evaluated=True, db_path=db)
    assert len(rows) == 1


# ============================================================
# 4. issue 倒退：不向后推进 last_processed 标记
# ============================================================

def test_issue_regression_keeps_marker(monkeypatch, sandbox):
    set_calls = {}

    def fake_set_meta(key, value):
        set_calls.setdefault(key, []).append(value)

    monkeypatch.setattr(es, "_set_meta", fake_set_meta)
    _isolate_daily(monkeypatch, [{"issue": 100, "front": [], "back": [], "date": ""}],
                   last_processed="105", target_saved=False)  # 历史倒退：105 > 100
    es.run_daily()
    # 不应将 last_processed_issue 回写为更低的 100
    assert "100" not in set_calls.get("last_processed_issue", [])
    # 若有写入，应保持原位点（此处不应写入更低值）
    for v in set_calls.get("last_processed_issue", []):
        assert int(v) >= 105


# ============================================================
# 5. 单任务失败隔离
# ============================================================

def test_single_task_failure_isolated(monkeypatch, sandbox):
    def boom():
        raise RuntimeError("boom")

    def ok():
        return None

    s1 = es._run_task("boom", "daily", boom)
    s2 = es._run_task("ok", "daily", ok)
    assert s1 == es.STATUS_FAILED
    assert s2 == es.STATUS_SUCCESS
    assert es._overall_status([s1, s2]) == es.STATUS_PARTIAL
    assert es._overall_status([s2, s2]) == es.STATUS_SUCCESS
    assert es._overall_status([s1, s1]) == es.STATUS_FAILED


# ============================================================
# 6. 生产冻结文件变更 → 守卫判定 BLOCKED
# ============================================================

def test_prod_change_guard_blocks():
    pre = {"src/scorer.py": "abc", "data/structure_profile.json": "def"}
    post_same = dict(pre)
    post_changed = dict(pre)
    post_changed["src/scorer.py"] = "XYZ"  # 生产源码被改
    assert prod_guard_blocked(pre, post_same) is False
    assert prod_guard_blocked(pre, post_changed) is True

    # ABSENT 基线：出现新生产文件也视为变更
    pre_abs = {"data/recommendations.json": "ABSENT"}
    post_abs = {"data/recommendations.json": "present-hash"}
    assert prod_guard_blocked(pre_abs, post_abs) is True


# ============================================================
# 7. canonical structure_profile 不被实验污染 + 守卫
# ============================================================

def test_canonical_structure_profile_untouched_and_guard(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="dlt_pipe_")
    monkeypatch.chdir(tmp)
    # 构造小型历史（60 期），足以驱动 run_pipeline 预测
    issues = []
    for i in range(60):
        issues.append({
            "issue": 19075 + i,
            "front": [(i % 30) + 1, (i % 28) + 2, (i % 26) + 3, (i % 24) + 4, (i % 22) + 5],
            "back": [(i % 10) + 1, (i % 9) + 2],
            "date": f"2026-01-{i % 28 + 1:02d}",
        })
    os.makedirs("data", exist_ok=True)
    with open("data/dlt_history.json", "w", encoding="utf-8") as f:
        json.dump({"issues": issues}, f, ensure_ascii=False)
    # run_pipeline 需要 config/settings.yaml，复制到沙箱
    import shutil
    settings_src = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    if os.path.exists(settings_src):
        os.makedirs("config", exist_ok=True)
        shutil.copyfile(settings_src, "config/settings.yaml")

    # 运行真实 run_pipeline（无 monkeypatch），观察是否改写 canonical 画像
    import src.daily_prediction_pipeline as dp
    dp.run_pipeline()

    # canonical 画像不应被写入（generate_structure_profile 默认落到临时 scratch）
    assert not os.path.exists("data/structure_profile.json"), \
        "run_pipeline 不应生成 canonical data/structure_profile.json"
    # 实验库应已写入
    assert os.path.exists("data/experiments.sqlite")

    # 守卫逻辑：若 structure_profile.json 出现/变化 → BLOCKED
    pre = {"data/structure_profile.json": "ABSENT"}
    post = {"data/structure_profile.json": "new-hash"}
    assert prod_guard_blocked(pre, post) is True


# ============================================================
# 8. 展示数据：报告缺失 → status=unavailable（不死）
# ============================================================

def test_display_missing_report_fallback(monkeypatch):
    import scripts.build_experiment_display_data as b
    tmp = tempfile.mkdtemp(prefix="dlt_bld_")
    reports = os.path.join(tmp, "reports")
    out = os.path.join(tmp, "public", "data")
    os.makedirs(reports, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    # 仅提供 model_ranking.json，缺失其余报告
    with open(os.path.join(reports, "model_ranking.json"), "w", encoding="utf-8") as f:
        json.dump({"ranking": []}, f)
    monkeypatch.setattr(b, "REPORTS", reports)
    monkeypatch.setattr(b, "OUT", out)

    b.main()  # 不应抛异常

    # 存在的报告应被复制
    assert os.path.exists(os.path.join(out, "model_ranking.json"))
    # 缺失的反事实报告应生成 unavailable 占位
    cf = os.path.join(out, "phase15_counterfactual.json")
    assert os.path.exists(cf)
    with open(cf, "r", encoding="utf-8") as f:
        obj = json.load(f)
    assert obj.get("status") == "unavailable"


# ============================================================
# 9. save_experiment 同 (issue,model) 幂等
# ============================================================

def test_save_experiment_sqlite_idempotent(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="dlt_store2_")
    db = os.path.join(tmp, "experiments.sqlite")
    recs = [{"front": [1,2,3,4,5], "back": [6,7]}]
    store.save_experiment("555", "v2", parameters={}, recommendations=recs, db_path=db)
    store.save_experiment("555", "v2", parameters={"x": 1}, recommendations=[{"front":[9,8,7,6,5],"back":[1,2]}], db_path=db)
    rows = store.query_history(issue="555", db_path=db)
    assert len(rows) == 1  # INSERT OR IGNORE 生效


# ============================================================
# 10. 日任务不触发 walk-forward 全量重回放
# ============================================================

def test_daily_no_full_backfill(monkeypatch, sandbox):
    recorded = []

    def fake_subprocess(module):
        recorded.append(module)
        return []

    monkeypatch.setattr(es, "_subprocess", fake_subprocess)
    # 注意：保留 _build_display 真实实现，使其调用 _subprocess 被记录；
    # 仅隔离其它重度依赖。
    monkeypatch.setattr(es, "_load_history", lambda: [{"issue": 100, "front": [], "back": [], "date": ""}])
    monkeypatch.setattr(es, "_get_meta", lambda k: None)
    monkeypatch.setattr(es, "_target_fully_saved", lambda issue: False)
    monkeypatch.setattr(es, "_ensure_random_baseline", lambda *a, **k: None)
    monkeypatch.setattr(es, "_daily_reports", lambda: [])
    monkeypatch.setattr(es, "evaluate_draw_result", lambda *a, **k: None)
    monkeypatch.setattr(es, "query_history", lambda *a, **k: [])
    _stub_pipeline(monkeypatch)
    es.run_daily()
    assert "src.history_experiment_runner" not in recorded
    # build 展示是日任务允许的轻量子进程
    assert "scripts.build_experiment_display_data" in recorded


# ============================================================
# 11. 周任务触发指定的重度子任务
# ============================================================

def test_weekly_runs_specified_modules(monkeypatch, sandbox):
    recorded = []

    def fake_subprocess(module):
        recorded.append(module)
        return []

    monkeypatch.setattr(es, "_subprocess", fake_subprocess)
    monkeypatch.setattr(es, "_aggregate_counterfactual", lambda: [])
    monkeypatch.setattr(es, "_daily_reports", lambda: [])
    monkeypatch.setattr(es, "_build_display", lambda: [])
    monkeypatch.setattr(es, "query_history", lambda *a, **k: [])

    es.run_weekly()
    expected = [
        "src.history_experiment_runner",
        "src.random_baseline_runner",
        "src.entertainment_constrained_validator",
        "src.feature_ablation",
        "src.strategy_removal",
        "src.ensemble_comparison",
    ]
    for m in expected:
        assert m in recorded, f"周任务未触发 {m}"


# ============================================================
# 12. 手动任务仅产出审阅建议，不碰生产推荐
# ============================================================

def test_manual_review_only(monkeypatch, sandbox):
    monkeypatch.chdir(sandbox)
    real_exists = os.path.exists
    # 仅让 run_manual 内部对 step3 验证报告判为不存在；其余路径走真实 exists
    monkeypatch.setattr(os.path, "exists",
                        lambda p: False if "phase16_step3_validation.json" in p else real_exists(p))
    monkeypatch.setattr("src.model_evaluator.evaluate_models",
                        lambda *a, **k: {"ranking": ["v1"], "models": {"v1": {"composite": 0.0}, "random": {"composite": 0.0}}})
    monkeypatch.setattr("src.entertainment_evaluator.evaluate_entertainment",
                        lambda *a, **k: {"ranking": []})

    status = es.run_manual()
    assert status == es.STATUS_SUCCESS
    out = os.path.join(sandbox, "reports", "RECOMMENDATION_FOR_REVIEW.json")
    assert os.path.exists(out)
    with open(out, "r", encoding="utf-8") as f:
        obj = json.load(f)
    assert obj.get("binding") is False
    # 绝不写生产推荐文件
    assert not os.path.exists(os.path.join(sandbox, "public", "data", "recommendations.json"))
    assert not os.path.exists(os.path.join(sandbox, "reports", "recommendations.json"))


# ============================================================
# 13. random 基线缺失不导致生产失败
# ============================================================

def test_random_missing_no_prod_failure(monkeypatch, sandbox):
    monkeypatch.setattr(es, "_ensure_random_baseline",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("random missing")))
    _isolate_daily(monkeypatch, [{"issue": 100, "front": [], "back": [], "date": ""}],
                   last_processed=None, target_saved=False)
    # 不应抛异常；整体状态不应为 FAILED（random 失败被隔离）
    status = es.run_daily()
    assert status != es.STATUS_FAILED


# ============================================================
# 14. 调度器自身异常被兜底，退出非 0，不污染生产
# ============================================================

def test_scheduler_self_failure_exits_nonzero(monkeypatch, sandbox):
    monkeypatch.setattr(es, "run_daily", lambda: (_ for _ in ()).throw(RuntimeError("scheduler boom")))
    with pytest.raises(SystemExit) as exc:
        monkeypatch.setattr(sys, "argv", ["x", "--daily"])
        es.main()
    assert exc.value.code == 1
