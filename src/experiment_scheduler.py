"""实验任务调度器（Phase 16 Step 5 · 纯实验层模块）。

三层自动化：
  --daily   : 开奖后自动更新（秒级~分钟级）。
              增量追加实验库（评估新开奖期 + 预测目标期，含 random 基线）
              + 重算轻量报告（ranking / entertainment / diagnostics / feature_gain）
              + 生成展示 JSON（build 脚本）。
  --weekly  : 周期性重回放 / 重验证（数十分钟）。
              history 全量回放 / random 全量回填 / constrained 稳定性 /
              feature_ablation / strategy_removal / ensemble_comparison / 反事实聚合。
  --manual  : 人工批准任务。仅生成 reports/RECOMMENDATION_FOR_REVIEW.json，
              绝不修改生产、绝不自动调权、绝不替换推荐。

硬性约束（务必遵守）：
  - 不修改 scorer.py / recommender.py / scheduler.py / publisher.py。
  - 不修改 data/recommendations.json（生产推荐）；不写 config/adaptive_weights.yaml。
  - 每个实验独立 try/except；单实验失败不影响其他实验，也不影响生产推荐流程。
  - 复用 experiments.sqlite 现有幂等设计（INSERT OR IGNORE + evaluate_draw_result
    跳过已评估），不改 experiment_store。
  - 任何异常均被捕获并记录，绝不让实验失败冒泡到生产流程。

状态机（Step 7）：
  SUCCESS / PARTIAL_SUCCESS / NO_NEW_DATA / FAILED
  （BLOCKED_PRODUCTION_CHANGE 由 CI 保护步骤强制判定，不在此模块内。）

运行记录：写入 data/experiment_runs.sqlite（与 experiments.sqlite 分离的元数据库，
避免污染实验数据表）。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HISTORY_PATH = "data/dlt_history.json"
RUN_DB = "data/experiment_runs.sqlite"
PY = sys.executable

KNOWN_MODELS = ("v1", "v2", "adaptive", "random")

# 轻量导入（experiment_store 为纯实验层，不依赖生产逻辑）
from .experiment_store import evaluate_draw_result, query_history  # noqa: E402

# 日轻量报告（读 experiments.sqlite，无重预测）
DAILY_REPORTS = [
    "reports/model_ranking.json",
    "reports/entertainment_evaluation.json",
    "reports/model_diagnostic_report.json",
    "reports/reward_stability_report.json",
    "reports/feature_gain_report.json",
]

STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL = "PARTIAL_SUCCESS"
STATUS_NO_NEW = "NO_NEW_DATA"
STATUS_FAILED = "FAILED"


# ============================================================
# 运行记录库（data/experiment_runs.sqlite）
# ============================================================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect_run_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(RUN_DB) or ".", exist_ok=True)
    conn = sqlite3.connect(RUN_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT,
            task TEXT,
            started_at TEXT,
            ended_at TEXT,
            duration_s REAL,
            status TEXT,
            error TEXT,
            output_files TEXT,
            coverage_periods INTEGER
        )
        """
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()
    return conn


def _set_meta(key: str, value: str) -> None:
    conn = _connect_run_db()
    try:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def _get_meta(key: str) -> str | None:
    conn = _connect_run_db()
    try:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _insert_run_log(
    mode: str,
    task: str,
    started: str,
    ended: str,
    duration_s: float,
    status: str,
    error: str | None,
    output_files: list[str],
    coverage_periods: int | None,
) -> None:
    conn = _connect_run_db()
    try:
        conn.execute(
            "INSERT INTO run_log(mode, task, started_at, ended_at, duration_s, "
            "status, error, output_files, coverage_periods) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                mode,
                task,
                started,
                ended,
                round(duration_s, 3),
                status,
                error,
                json.dumps(output_files, ensure_ascii=False),
                coverage_periods,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 任务包装（失败隔离）
# ============================================================

def _run_task(name: str, mode: str, fn: Callable[[], Any]) -> str:
    """执行单个实验任务，捕获异常，记录到 run_log。

    参数：
        fn: 无参 callable；成功可返回 output_files(list[str]) 或 None。
            任何异常都被捕获，任务状态记为 FAILED，不影响其他任务。
    返回：
        STATUS_SUCCESS / STATUS_FAILED
    """
    started = _now()
    t0 = time.time()
    error: str | None = None
    outputs: list[str] = []
    try:
        r = fn()
        if isinstance(r, list):
            outputs = r
    except Exception as e:  # 单任务失败隔离
        error = f"{type(e).__name__}: {e}"
    ended = _now()
    duration = time.time() - t0
    status = STATUS_FAILED if error else STATUS_SUCCESS
    _insert_run_log(mode, name, started, ended, duration, status, error, outputs, None)
    if error:
        print(f"[experiment_scheduler] ⚠️ 任务 {name} 失败（已隔离）: {error}")
    else:
        print(f"[experiment_scheduler] ✅ 任务 {name} 完成 ({duration:.1f}s)")
    return status


def _coverage_periods() -> int:
    """experiments.sqlite 中已评估期数（数据覆盖期数）。"""
    try:
        rows = query_history(only_evaluated=True)
        return len(rows)
    except Exception:
        return -1


def _overall_status(statuses: list[str]) -> str:
    """由各任务状态汇总整体状态（Step 7 状态机）。"""
    if not statuses:
        return STATUS_SUCCESS
    if all(s == STATUS_FAILED for s in statuses):
        return STATUS_FAILED
    if any(s == STATUS_FAILED for s in statuses):
        return STATUS_PARTIAL
    return STATUS_SUCCESS


def _subprocess(module: str) -> list[str]:
    """以子进程运行一个实验模块（进程级隔离），成功返回 []，失败抛异常。"""
    rc = subprocess.run(
        [PY, "-m", module],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if rc.returncode != 0:
        msg = (rc.stderr or rc.stdout or "")[-800:]
        raise RuntimeError(f"{module} exit={rc.returncode}: {msg}")
    return []


# ============================================================
# 数据装载 / 增量判定
# ============================================================

def _load_history() -> list[dict]:
    """读取生产历史开奖（data/dlt_history.json）。

    返回按 issue 升序的列表，每项为 {issue, front, back, date}。
    异常返回空列表（调用方据此判 FAILED，不崩溃）。
    """
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
        issues = db.get("issues", [])
        return sorted(issues, key=lambda x: int(x.get("issue", 0)))
    except Exception as e:
        print(f"[experiment_scheduler] 读取历史失败: {e}")
        return []


def _is_evaluated(issue: str) -> bool:
    from .experiment_store import query_history
    rows = query_history(issue=str(issue), only_evaluated=True)
    return len(rows) > 0


def _target_fully_saved(target_issue: str) -> bool:
    from .experiment_store import query_history
    rows = query_history(issue=str(target_issue))
    saved = {r["model_version"] for r in rows}
    return all(m in saved for m in KNOWN_MODELS)


# ============================================================
# DAILY
# ============================================================

def _ensure_random_baseline(target_issue: str, n_bets: int = 5, seed: int = 123) -> None:
    """为目标期生成 random 基线并写入实验库（daily_prediction_pipeline 未覆盖）。"""
    from .random_baseline_runner import generate_random_tickets
    from .experiment_store import save_experiment
    recs = generate_random_tickets(n_bets, seed)
    save_experiment(str(target_issue), "random", parameters={}, recommendations=recs)
    print(f"[experiment_scheduler] random 基线已写入目标期 {target_issue}")


def _daily_reports() -> list[str]:
    """重算日轻量报告（读 sqlite，无重预测）。每个失败不影响其他。"""
    statuses: list[str] = []

    def _ranking():
        from .model_evaluator import generate_ranking_report
        generate_ranking_report()
        return ["reports/model_ranking.json"]

    def _ent():
        from .entertainment_evaluator import evaluate_entertainment
        evaluate_entertainment()
        return ["reports/entertainment_evaluation.json"]

    def _diag():
        from .model_diagnostics import (
            generate_diagnostic_report,
            generate_reward_stability_report,
        )
        generate_diagnostic_report()
        generate_reward_stability_report()
        return ["reports/model_diagnostic_report.json", "reports/reward_stability_report.json"]

    def _feat():
        from .feature_contribution_analyzer import generate_feature_gain_report
        generate_feature_gain_report()
        return ["reports/feature_gain_report.json"]

    for name, fn in (
        ("model_ranking", _ranking),
        ("entertainment", _ent),
        ("diagnostics", _diag),
        ("feature_gain", _feat),
    ):
        statuses.append(_run_task(name, "daily", fn))
    return statuses


def _build_display() -> list[str]:
    """生成展示 JSON（容忍缺失报告，详见 build 脚本改造）。"""
    _subprocess("scripts.build_experiment_display_data")
    return ["public/data/*.json"]


def run_daily() -> str:
    """每日轻量任务。返回整体状态。"""
    print(f"[experiment_scheduler] === DAILY 开始 {_now()} ===")
    history = _load_history()
    if not history:
        _set_meta("last_daily_status", STATUS_FAILED)
        return STATUS_FAILED

    latest_issue = str(history[-1]["issue"])
    target_issue = str(int(latest_issue) + 1)
    last_processed = _get_meta("last_processed_issue")

    # ---- 增量判定（Step 4）----
    new_issues = [
        h for h in history
        if last_processed is None or int(h["issue"]) > int(last_processed)
    ]
    target_saved = _target_fully_saved(target_issue)

    if not new_issues and target_saved:
        print(f"[experiment_scheduler] 无新开奖数据（latest={latest_issue}），NO_NEW_DATA")
        _set_meta("last_daily_status", STATUS_NO_NEW)
        _set_meta("last_daily_run", _now())
        return STATUS_NO_NEW

    if last_processed is not None and int(latest_issue) < int(last_processed):
        # issue 倒退：拒绝向后处理，仅记录告警（不删不改）
        print(f"[experiment_scheduler] ⚠️ 检测到 issue 倒退 "
              f"({latest_issue} < 已处理 {last_processed})，拒绝向后处理")

    # ---- 追评新开奖期（幂等）----
    statuses: list[str] = []
    for h in new_issues:
        issue = str(h["issue"])
        actual = {"front": h.get("front", []), "back": h.get("back", []), "date": h.get("date", "")}
        statuses.append(_run_task(
            f"evaluate_{issue}", "daily",
            lambda iss=issue, act=actual: evaluate_draw_result(iss, act) or None))

    # ---- 预测目标期（v1/v2/adaptive 经生产式日管道；random 单独补）----
    def _predict_target():
        from .daily_prediction_pipeline import run_pipeline
        run_pipeline()  # 评估 latest + 保存 target(v1/v2/adaptive) + 写展示
        return []

    statuses.append(_run_task("predict_target", "daily", _predict_target))
    statuses.append(_run_task("random_baseline", "daily",
                     lambda: _ensure_random_baseline(target_issue) or None))

    # ---- 重算轻量报告 + 生成展示 ----
    statuses.extend(_daily_reports())
    statuses.append(_run_task("build_display", "daily", _build_display))

    # ---- 更新 meta（issue 倒退时不向后推进标记，避免丢失已处理位点）----
    if last_processed is None or int(latest_issue) >= int(last_processed):
        _set_meta("last_processed_issue", latest_issue)
    else:
        print(f"[experiment_scheduler] 保持 last_processed_issue={last_processed}"
              f"（检测到倒退，不向后推进）")
    _set_meta("last_daily_run", _now())
    cov = _coverage_periods()
    _set_meta("last_coverage_periods", str(cov))

    # ---- 整体状态（Step 7）----
    overall = _overall_status(statuses)
    print(f"[experiment_scheduler] === DAILY 完成 {_now()} "
          f"（覆盖 {cov} 期，target={target_issue}，整体 {overall}）===")
    _set_meta("last_daily_status", overall)
    return overall


# ============================================================
# WEEKLY
# ============================================================

def _aggregate_counterfactual() -> list[str]:
    """聚合三类反事实子报告为 counterfactual_analysis.json（aggregate_report 当前无自动调用）。"""
    from .counterfactual_common import aggregate_report
    subs = {
        "feature": "reports/counterfactual_feature_ablation.json",
        "strategy": "reports/counterfactual_strategy_removal.json",
        "ensemble": "reports/counterfactual_ensemble_comparison.json",
    }
    if not all(os.path.exists(p) for p in subs.values()):
        missing = [k for k, v in subs.items() if not os.path.exists(v)]
        raise RuntimeError(f"反事实子报告缺失: {missing}")
    with open(subs["feature"], "r", encoding="utf-8") as f:
        fr = json.load(f)
    with open(subs["strategy"], "r", encoding="utf-8") as f:
        sr = json.load(f)
    with open(subs["ensemble"], "r", encoding="utf-8") as f:
        er = json.load(f)
    aggregate_report(fr, sr, er)
    return ["reports/counterfactual_analysis.json"]


def run_weekly() -> str:
    """每周重度任务。返回整体状态。"""
    print(f"[experiment_scheduler] === WEEKLY 开始 {_now()} ===")
    statuses: list[str] = []
    # 重度 walk-forward / 重回放（子进程隔离，单任务失败不影响其他）
    heavy = [
        ("history_backfill", "src.history_experiment_runner"),
        ("random_backfill", "src.random_baseline_runner"),
        ("constrained_stability", "src.entertainment_constrained_validator"),
        ("feature_ablation", "src.feature_ablation"),
        ("strategy_removal", "src.strategy_removal"),
        ("ensemble_comparison", "src.ensemble_comparison"),
    ]
    for name, module in heavy:
        statuses.append(_run_task(name, "weekly", lambda m=module: _subprocess(m)))

    # 反事实聚合
    statuses.append(_run_task("counterfactual_aggregate", "weekly", _aggregate_counterfactual))

    # 轻量报告 + 展示（与 daily 共享）
    statuses.extend(_daily_reports())
    statuses.append(_run_task("build_display", "weekly", _build_display))

    _set_meta("last_weekly_run", _now())
    cov = _coverage_periods()
    _set_meta("last_coverage_periods", str(cov))
    overall = _overall_status(statuses)
    print(f"[experiment_scheduler] === WEEKLY 完成 {_now()}（覆盖 {cov} 期，整体 {overall}）===")
    _set_meta("last_weekly_status", overall)
    return overall


# ============================================================
# MANUAL（仅生成 RECOMMENDATION_FOR_REVIEW，绝不改生产）
# ============================================================

def run_manual() -> str:
    """人工批准任务：汇总当前实验结论，产出仅供人工审阅的建议文件。

    绝不修改生产推荐、绝不写 adaptive_weights.yaml、绝不自动调权。
    """
    print(f"[experiment_scheduler] === MANUAL 开始 {_now()} ===")
    out_path = "reports/RECOMMENDATION_FOR_REVIEW.json"

    try:
        from .model_evaluator import evaluate_models
        from .entertainment_evaluator import evaluate_entertainment

        models = evaluate_models()
        ent = evaluate_entertainment()

        ranking = models.get("ranking", [])
        beats_random = {
            mv: models["models"][mv]["composite"]
            > models["models"].get("random", {}).get("composite", 0.0)
            for mv in ranking
        }
        # 读取稳定性验证结论（若存在）
        step3 = None
        if os.path.exists("reports/phase16_step3_validation.json"):
            with open("reports/phase16_step3_validation.json", "r", encoding="utf-8") as f:
                step3 = json.load(f)

        review = {
            "generated_at": _now(),
            "mode": "manual",
            "binding": False,
            "note": "本文件仅供人工审阅。实验系统不自动修改生产评分权重、"
                    "不替换生产推荐、不启用任何候选策略。任何变更需人工确认后实施。",
            "model_ranking": ranking,
            "beats_random": beats_random,
            "entertainment_ranking": [
                {"model": r["model"], "ux_score": r["ux_score"]}
                for r in ent.get("ranking", [])
            ],
            "stability_verdict": (
                step3.get("stability_verdict") if step3 else "N/A（未运行稳定性验证）"
            ),
            "recommendations": [
                "当前所有模型 composite 均未稳健超越 random 基线，"
                "依据 Phase 15/16 结论，不建议自动修改 scorer 权重。",
                "coverage_boost 在多窗口×多种子稳定性验证中判为不稳定"
                "（pass_rate=0.5），不建议作为实验展示策略启用。",
                "如未来要启用任一候选策略或调整权重，须经人工评审并显式确认。",
            ],
        }
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(review, f, ensure_ascii=False, indent=2)
        print(f"[experiment_scheduler] 已生成人工审阅文件: {out_path}")
    except Exception as e:
        print(f"[experiment_scheduler] ⚠️ MANUAL 生成失败（已隔离）: {e}")
        _set_meta("last_manual_status", STATUS_FAILED)
        return STATUS_FAILED

    _set_meta("last_manual_run", _now())
    _set_meta("last_manual_status", STATUS_SUCCESS)
    print(f"[experiment_scheduler] === MANUAL 完成（仅产出审阅建议，未改动生产）===")
    return STATUS_SUCCESS


# ============================================================
# 入口
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="实验任务调度器（Phase 16 Step 5）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daily", action="store_true", help="每日轻量更新")
    group.add_argument("--weekly", action="store_true", help="每周重度重验证")
    group.add_argument("--manual", action="store_true", help="生成人工审阅建议")
    args = parser.parse_args()

    try:
        if args.daily:
            status = run_daily()
        elif args.weekly:
            status = run_weekly()
        else:
            status = run_manual()
    except Exception as e:
        # 顶层兜底：调度器自身异常不得冒泡为生产失败
        print(f"[experiment_scheduler] 调度器异常（已记录，不影响生产）: "
              f"{type(e).__name__}: {e}")
        status = STATUS_FAILED

    print(f"[experiment_scheduler] 退出状态: {status}")
    # 退出码：NO_NEW_DATA / SUCCESS / PARTIAL 均视为成功（0），仅 FAILED 非 0。
    # 注意：PARTIAL_SUCCESS 也返回 0，避免 CI 因单实验失败而阻断生产提交。
    sys.exit(0 if status != STATUS_FAILED else 1)


if __name__ == "__main__":
    main()
