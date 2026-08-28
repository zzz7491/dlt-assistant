#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实验运行状态监控（Phase 16 Step 6 · 纯实验层模块）。

职责：
- 只读取 data/experiment_runs.sqlite（由 experiment_scheduler 写入的运行记录库）。
- 聚合 experimental 自动化任务的运行情况，输出 reports/experiment_run_status.json。
- 不修改 experiments.sqlite，不修改 experiment_runs.sqlite，不调用任何生产模块
  （scorer / recommender / scheduler / publisher），不写任何生产文件。

健壮性（失败隔离）：
- 数据库不存在 / 为空 / 损坏 / 字段异常 / 任意意外错误，
  都转换为结构化 status=unavailable | error，并写入 fatal_error 字段，
  绝不抛出未捕获异常导致调用方（CI / 生产提交）崩溃。

运行记录 schema（来自 experiment_scheduler._connect_run_db，不猜测）：
  run_log(id, mode, task, started_at, ended_at, duration_s, status, error,
          output_files, coverage_periods)
  meta(key TEXT PRIMARY KEY, value TEXT)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 允许测试注入临时库路径
RUN_DB = os.environ.get("EXPERIMENT_RUN_DB", os.path.join(ROOT, "data", "experiment_runs.sqlite"))
OUT_PATH = os.environ.get(
    "EXPERIMENT_RUN_STATUS_OUT",
    os.path.join(ROOT, "reports", "experiment_run_status.json"),
)

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"


def _empty_status(note: str, status: str = STATUS_UNAVAILABLE, fatal_error=None) -> dict:
    return {
        "status": status,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": RUN_DB,
        "monitor_note": note,
        "overall_status": "UNKNOWN",
        "total_runs": 0,
        "last_run_time": None,
        "modes": {
            "daily": {"last_status": None, "last_run": None, "total": 0},
            "weekly": {"last_status": None, "last_run": None, "total": 0},
            "manual": {"last_status": None, "last_run": None, "total": 0},
        },
        "task_stats": {},
        "last_failed_task": None,
        "last_error": None,
        "coverage_periods": None,
        "fatal_error": fatal_error,
    }


def build_status(db_path: str = RUN_DB) -> dict:
    """读取运行记录库并聚合为状态 dict；任何异常均被捕获并降级。"""
    # 1) 数据库不存在
    if not os.path.exists(db_path):
        return _empty_status(
            "运行记录库尚未生成（experiment_scheduler 未运行过）。"
            "实验自动化尚未产生运行数据，属正常初始状态。",
            STATUS_UNAVAILABLE,
        )

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # 2) 读取 run_log（可能表不存在 → 视为空库）
        try:
            rows = cur.execute(
                "SELECT id, mode, task, started_at, ended_at, duration_s, "
                "status, error, output_files, coverage_periods "
                "FROM run_log ORDER BY id ASC"
            ).fetchall()
        except sqlite3.OperationalError:
            # 仅表不存在视为空库（新调度器尚未运行）；损坏属 DatabaseError 由外层捕获
            rows = []
        # 读取 meta 键值
        try:
            meta_rows = cur.execute("SELECT key, value FROM meta").fetchall()
            meta = {r["key"]: r["value"] for r in meta_rows}
        except sqlite3.OperationalError:
            meta = {}
        conn.close()
    except sqlite3.Error as e:
        # 3) 数据库损坏 / 无法打开
        return _empty_status(
            "运行记录库读取失败（可能损坏或无法打开）。",
            STATUS_ERROR,
            fatal_error=f"{type(e).__name__}: {e}",
        )
    except Exception as e:  # 其它意外
        return _empty_status(
            "运行记录库解析时发生意外错误。",
            STATUS_ERROR,
            fatal_error=f"{type(e).__name__}: {e}",
        )

    # 4) 空库（表存在但无记录）
    if not rows:
        st = _empty_status(
            "运行记录库已存在但无任何运行记录（experiment_scheduler 尚未成功运行）。",
            STATUS_UNAVAILABLE,
        )
        # 仍把 meta 中的状态透出（便于观察最近一次失败标记）
        st["modes"]["daily"]["last_status"] = meta.get("last_daily_status")
        st["modes"]["weekly"]["last_status"] = meta.get("last_weekly_status")
        st["modes"]["manual"]["last_status"] = meta.get("last_manual_status")
        return st

    # 5) 聚合
    total_runs = len(rows)
    modes = {
        "daily": {"last_status": None, "last_run": None, "total": 0},
        "weekly": {"last_status": None, "last_run": None, "total": 0},
        "manual": {"last_status": None, "last_run": None, "total": 0},
    }
    task_stats: dict[str, dict[str, int]] = {}
    last_failed_task: str | None = None
    last_error: str | None = None
    last_run_time: str | None = None
    coverage_periods: int | None = None

    for r in rows:
        mode = (r["mode"] or "unknown").lower()
        task = r["task"]
        status_v = r["status"]
        # 模式计数
        if mode in modes:
            modes[mode]["total"] += 1
            # 以最大 id（最后写入）作为该模式最近状态
            if modes[mode]["last_run"] is None or (r["ended_at"] or "") >= modes[mode]["last_run"]:
                modes[mode]["last_run"] = r["ended_at"]
                modes[mode]["last_status"] = status_v
        # 任务统计
        if task not in task_stats:
            task_stats[task] = {"success": 0, "failed": 0}
        if status_v == "FAILED":
            task_stats[task]["failed"] += 1
            last_failed_task = task
            last_error = r["error"]
        else:
            task_stats[task]["success"] += 1
        # 最近运行时间（按 ended_at 取最大）
        if r["ended_at"]:
            if last_run_time is None or r["ended_at"] > last_run_time:
                last_run_time = r["ended_at"]
        # 覆盖期数（取最近一次非空 coverage_periods）
        cov = r["coverage_periods"]
        if cov is not None:
            try:
                coverage_periods = int(cov)
            except (TypeError, ValueError):
                pass

    # 用 meta 兜底覆盖（run_log 中 coverage_periods 可能为 None）
    if coverage_periods is None and meta.get("last_coverage_periods"):
        try:
            coverage_periods = int(meta["last_coverage_periods"])
        except (TypeError, ValueError):
            coverage_periods = None

    # 整体状态：任意 FAILED 存在即 PARTIAL/DEGRADED 标记（仅作展示）
    any_failed = any(s["failed"] > 0 for s in task_stats.values())
    overall = "DEGRADED" if any_failed else "HEALTHY"

    return {
        "status": STATUS_OK,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": db_path,
        "monitor_note": "聚合自 experiment_scheduler 运行记录；仅实验层可观测性，"
                        "不参与生产推荐决策。",
        "overall_status": overall,
        "total_runs": total_runs,
        "last_run_time": last_run_time,
        "modes": modes,
        "task_stats": task_stats,
        "last_failed_task": last_failed_task,
        "last_error": last_error,
        "coverage_periods": coverage_periods,
        "fatal_error": None,
    }


def main() -> int:
    """写入 reports/experiment_run_status.json；任何异常均被捕获，绝不崩溃。"""
    try:
        status = build_status(RUN_DB)
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        print(f"[experiment_monitor] 已生成运行状态: {OUT_PATH} (status={status['status']})")
        return 0
    except Exception as e:  # 终极兜底
        try:
            os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    _empty_status("monitor 自身异常", STATUS_ERROR,
                                  fatal_error=f"{type(e).__name__}: {e}"),
                    f, ensure_ascii=False, indent=2,
                )
            print(f"[experiment_monitor] ⚠️ monitor 异常已隔离并写入 error 状态: {e}")
        except Exception:
            pass
        return 0  # 失败隔离：monitor 失败不得导致 CI 非零退出


if __name__ == "__main__":
    sys.exit(main())
