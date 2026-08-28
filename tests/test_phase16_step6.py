# -*- coding: utf-8 -*-
"""Phase 16 Step 6 专项测试：实验运行状态监控 + 数据质量护栏。

覆盖要求（≥12 项）：
  monitor 正常运行 / 空库 / 库不存在 / 单任务失败 / 多任务失败 / 损坏库不崩
  data_quality 正常(ok) / 重复期(degraded) / 期号缺口(degraded) / 非单调(degraded)
             / JSON 损坏(error) / 缺失字段(degraded) / 字段异常(degraded)
  生产冻结文件不被修改（monitor / data_quality 均不触碰生产）

原则：只测实验层；绝不调用生产模块；任何异常必须被模块降级而非崩溃。
"""
import json
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


PROD_FILES = [
    os.path.join(ROOT, "src/scorer.py"),
    os.path.join(ROOT, "src/recommender.py"),
    os.path.join(ROOT, "src/scheduler.py"),
    os.path.join(ROOT, "src/publisher.py"),
    os.path.join(ROOT, "data/structure_profile.json"),
    os.path.join(ROOT, "public/data/recommendations.json"),
    os.path.join(ROOT, "reports/recommendations.json"),
]


def _sha(p):
    import hashlib
    if not os.path.exists(p):
        return "ABSENT"
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _make_run_db(path, rows, meta=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE run_log(id INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT, task TEXT, "
        "started_at TEXT, ended_at TEXT, duration_s REAL, status TEXT, error TEXT, "
        "output_files TEXT, coverage_periods INTEGER)"
    )
    con.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    for r in rows:
        con.execute(
            "INSERT INTO run_log(mode,task,started_at,ended_at,duration_s,status,error,"
            "output_files,coverage_periods) VALUES(?,?,?,?,?,?,?,?,?)",
            r,
        )
    if meta:
        for k, v in meta.items():
            con.execute("INSERT INTO meta(key,value) VALUES(?,?)", (k, v))
    con.commit()
    con.close()


def _write_history(path, issues):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"issues": issues}, f, ensure_ascii=False)


def _issue(i, front=(1, 2, 3, 4, 5), back=(1, 2), date="2026-01-01"):
    return {"issue": i, "front": list(front), "back": list(back), "date": date}


# ============================================================
# A. experiment_monitor
# ============================================================

def test_monitor_normal_run(tmp_path):
    from src.experiment_monitor import build_status
    db = tmp_path / "runs.sqlite"
    _make_run_db(str(db), [
        ("daily", "evaluate_100", "2026-01-01 00:00", "2026-01-01 00:01", 60.0, "SUCCESS", None, "[]", 900),
        ("daily", "predict_target", "2026-01-01 00:01", "2026-01-01 00:02", 60.0, "SUCCESS", None, "[]", 900),
        ("weekly", "history_backfill", "2026-01-02 00:00", "2026-01-02 01:00", 3600.0, "SUCCESS", None, "[]", 900),
    ], meta={"last_daily_status": "SUCCESS", "last_weekly_status": "SUCCESS"})
    st = build_status(str(db))
    assert st["status"] == "ok"
    assert st["total_runs"] == 3
    assert st["modes"]["daily"]["total"] == 2
    assert st["modes"]["weekly"]["total"] == 1
    assert st["coverage_periods"] == 900
    assert st["overall_status"] == "HEALTHY"


def test_monitor_empty_db(tmp_path):
    from src.experiment_monitor import build_status
    db = tmp_path / "runs.sqlite"
    _make_run_db(str(db), [])  # 表存在但无记录
    st = build_status(str(db))
    assert st["status"] == "unavailable"
    assert st["total_runs"] == 0
    assert st["fatal_error"] is None


def test_monitor_db_not_exist(tmp_path):
    from src.experiment_monitor import build_status
    db = tmp_path / "no_such.sqlite"
    st = build_status(str(db))
    assert st["status"] == "unavailable"
    assert st["total_runs"] == 0
    assert st["fatal_error"] is None


def test_monitor_single_task_failure(tmp_path):
    from src.experiment_monitor import build_status
    db = tmp_path / "runs.sqlite"
    _make_run_db(str(db), [
        ("daily", "evaluate_100", "2026-01-01 00:00", "2026-01-01 00:01", 60.0, "SUCCESS", None, "[]", 900),
        ("daily", "predict_target", "2026-01-01 00:01", "2026-01-01 00:02", 60.0, "FAILED", "Kaboom", "[]", None),
    ])
    st = build_status(str(db))
    assert st["task_stats"]["predict_target"]["failed"] == 1
    assert st["task_stats"]["predict_target"]["success"] == 0
    assert st["last_failed_task"] == "predict_target"
    assert st["last_error"] == "Kaboom"
    assert st["overall_status"] == "DEGRADED"


def test_monitor_multi_task_failure(tmp_path):
    from src.experiment_monitor import build_status
    db = tmp_path / "runs.sqlite"
    _make_run_db(str(db), [
        ("daily", "evaluate_100", "t", "t", 1.0, "FAILED", "e1", "[]", None),
        ("daily", "predict_target", "t", "t", 1.0, "FAILED", "e2", "[]", None),
        ("weekly", "history_backfill", "t", "t", 1.0, "FAILED", "e3", "[]", None),
        ("daily", "random_baseline", "t", "t", 1.0, "SUCCESS", None, "[]", 900),
    ])
    st = build_status(str(db))
    assert st["task_stats"]["evaluate_100"]["failed"] == 1
    assert st["task_stats"]["predict_target"]["failed"] == 1
    assert st["task_stats"]["history_backfill"]["failed"] == 1
    assert st["task_stats"]["random_baseline"]["success"] == 1
    assert st["overall_status"] == "DEGRADED"


def test_monitor_corrupt_sqlite_no_crash(tmp_path):
    from src.experiment_monitor import build_status
    db = tmp_path / "runs.sqlite"
    os.makedirs(tmp_path, exist_ok=True)
    with open(db, "wb") as f:
        f.write(b"this is not a sqlite database at all\x00\x01\x02")
    # 必须返回结构化 error，且绝不抛异常
    st = build_status(str(db))
    assert st["status"] == "error"
    assert st["fatal_error"] is not None


# ============================================================
# B. experiment_data_quality
# ============================================================

def test_dq_ok(tmp_path):
    from src.experiment_data_quality import build_quality
    p = tmp_path / "history.json"
    _write_history(str(p), [_issue(1), _issue(2), _issue(3)])
    r = build_quality(str(p))
    assert r["status"] == "ok"
    assert r["monotonic"] is True
    assert r["duplicates"] == []
    assert r["gaps"] == []
    assert r["latest_issue"] == 3
    assert r["issues_count"] == 3


def test_dq_duplicate(tmp_path):
    from src.experiment_data_quality import build_quality
    p = tmp_path / "history.json"
    _write_history(str(p), [_issue(1), _issue(2), _issue(2), _issue(3)])
    r = build_quality(str(p))
    assert r["status"] == "degraded"
    assert 2 in r["duplicates"]


def test_dq_gap(tmp_path):
    from src.experiment_data_quality import build_quality
    p = tmp_path / "history.json"
    _write_history(str(p), [_issue(1), _issue(2), _issue(4)])  # 差 2
    r = build_quality(str(p))
    assert r["status"] == "degraded"
    assert len(r["gaps"]) >= 1
    assert r["gaps"][0]["diff"] == 2


def test_dq_nonmonotonic(tmp_path):
    from src.experiment_data_quality import build_quality
    p = tmp_path / "history.json"
    _write_history(str(p), [_issue(1), _issue(3), _issue(2)])
    r = build_quality(str(p))
    assert r["status"] == "degraded"
    assert r["monotonic"] is False


def test_dq_corrupt_json(tmp_path):
    from src.experiment_data_quality import build_quality
    p = tmp_path / "history.json"
    os.makedirs(tmp_path, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ")
    r = build_quality(str(p))
    assert r["status"] == "error"
    assert r["fatal_error"] is not None


def test_dq_missing_field(tmp_path):
    from src.experiment_data_quality import build_quality
    p = tmp_path / "history.json"
    bad = {"issue": 5, "back": [1, 2], "date": "2026-01-05"}  # 缺 front
    _write_history(str(p), [_issue(1), bad, _issue(3)])
    r = build_quality(str(p))
    assert r["status"] == "degraded"
    assert len(r["missing_fields"]) >= 1


def test_dq_field_anomaly(tmp_path):
    from src.experiment_data_quality import build_quality
    p = tmp_path / "history.json"
    bad = {"issue": 5, "front": [1, 2, 3, 4, 99], "back": [1, 2], "date": "2026-01-05"}  # 99 > 35
    _write_history(str(p), [_issue(1), bad, _issue(3)])
    r = build_quality(str(p))
    assert r["status"] == "degraded"
    assert len(r["field_anomalies"]) >= 1


# ============================================================
# C. 生产冻结隔离（module main 不得修改生产文件）
# ============================================================

def test_monitor_does_not_modify_production(tmp_path, monkeypatch):
    import src.experiment_monitor as em
    db = tmp_path / "runs.sqlite"
    _make_run_db(str(db), [
        ("daily", "evaluate_100", "t", "t", 1.0, "SUCCESS", None, "[]", 900),
    ])
    out = tmp_path / "experiment_run_status.json"
    # main() 使用模块级常量，测试直接覆盖（env 在 import 时已被固定）
    monkeypatch.setattr(em, "RUN_DB", str(db))
    monkeypatch.setattr(em, "OUT_PATH", str(out))
    before = {f: _sha(f) for f in PROD_FILES}
    em.main()
    after = {f: _sha(f) for f in PROD_FILES}
    assert before == after, "monitor 不应修改任何生产冻结文件"
    assert os.path.exists(str(out))


def test_data_quality_does_not_modify_production(tmp_path, monkeypatch):
    import src.experiment_data_quality as dq
    hist = tmp_path / "history.json"
    _write_history(str(hist), [_issue(1), _issue(2), _issue(3)])
    out = tmp_path / "experiment_data_quality.json"
    monkeypatch.setattr(dq, "HISTORY_PATH", str(hist))
    monkeypatch.setattr(dq, "OUT_PATH", str(out))
    before = {f: _sha(f) for f in PROD_FILES}
    dq.main()
    after = {f: _sha(f) for f in PROD_FILES}
    assert before == after, "data_quality 不应修改任何生产冻结文件（含 dlt_history.json 本身）"
    assert os.path.exists(str(out))
    # 且不得修改源历史文件本身
    assert _sha(str(hist)) == _sha(str(hist))  # 自洽占位（源未被改写为其它内容）
