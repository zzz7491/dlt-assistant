"""阶段 16 Task 1.1-C：轨 B 本地闭环（Python 分析 → SQL 生成 + 本地校验）。

流程：data/dlt_history.json → loader → metrics → scorer → writer
输出：
  .verify_tmp/analysis_inserts.sql   dlt_analysis 指标缓存 INSERT OR REPLACE
  .verify_tmp/scores_inserts.sql     dlt_scores 评分缓存 INSERT OR REPLACE
默认只生成 SQL（不直接写 D1）；写 D1 前请先检查 SQL（见 --check）。

用法：
  python scripts/analysis_run.py                     # 默认全窗口 [50,100,300,1000,all]
  python scripts/analysis_run.py --periods 100,all   # 自定义窗口
  python scripts/analysis_run.py --no-check          # 跳过本地 sqlite 校验
  python scripts/analysis_run.py --out-dir .verify_tmp

校验（--check，默认开启）在内存 sqlite 中执行 migrations/0001_init_dlt.sql 建表，
再执行生成的 SQL，验证：语法/表名/字段数/JSON 可解析/幂等（执行两遍行数不变）/
score TOP 与 Python 输出一致。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from analysis.loader import load_issues  # noqa: E402
from analysis.metrics import (calculate_frequency, calculate_hot, calculate_missing,  # noqa: E402
                              calculate_odd_even, calculate_big_small, calculate_consec)
from analysis.scorer import MODEL_TYPES, score_all  # noqa: E402
from analysis.writer import build_analysis_inserts, build_scores_inserts, write_sql_file  # noqa: E402

DATA_PATH = os.path.join(ROOT, "data", "dlt_history.json")
DDL_PATH = os.path.join(ROOT, "migrations", "0001_init_dlt.sql")

# 指标清单（metric 名与 V2-ROADMAP /api/analysis 约定一致）
METRICS = {
    "frequency": calculate_frequency,
    "hot": calculate_hot,
    "missing": calculate_missing,
    "oddEven": calculate_odd_even,
    "bigSmall": calculate_big_small,
    "consec": calculate_consec,
}
KINDS = ["front", "back"]
ANALYSIS_VERSION = "v1"
WEIGHT_VERSION = "default"
DEFAULT_PERIODS = [50, 100, 300, 1000, "all"]


def run_pipeline(periods: list) -> tuple[list, list, int, int]:
    """执行 loader→metrics→scorer→writer，返回 (analysis_statements, scores_statements, 期望行数A, 期望行数S)。"""
    issues = load_issues(path=DATA_PATH)
    n_issues = len(issues)
    print(f"[loader] 读取 {n_issues} 期（{issues[0]['issue']} ~ {issues[-1]['issue']}）")

    analysis_statements: list[str] = []
    for period in periods:
        for kind in KINDS:
            for metric, fn in METRICS.items():
                result = fn(issues, period, kind)
                analysis_statements.extend(
                    build_analysis_inserts(result, period, kind, metric, version=ANALYSIS_VERSION)
                )

    scores_statements: list[str] = []
    for period in periods:
        for kind in KINDS:
            for model in MODEL_TYPES:
                scores = score_all(issues, period, kind, model)
                scores_statements.extend(
                    build_scores_inserts(scores, period, kind, model, weight_version=WEIGHT_VERSION)
                )

    n_a = len(periods) * len(KINDS) * len(METRICS)
    # 每窗口：front 3 模型 × 35 号码 + back 3 模型 × 12 号码
    n_s = len(periods) * len(MODEL_TYPES) * (35 + 12)
    return analysis_statements, scores_statements, n_a, n_s


def _exec_sql(conn: sqlite3.Connection, path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        conn.executescript(fh.read())


def check_sql(analysis_path: str, scores_path: str, expect_a: int, expect_s: int,
              periods: list) -> dict:
    """内存 sqlite 校验：语法/表名/字段数/JSON/幂等/TOP 对照。"""
    report: dict = {}
    conn = sqlite3.connect(":memory:")
    try:
        # 建表（用真实 DDL，确保字段与 D1 一致）
        with open(DDL_PATH, encoding="utf-8") as fh:
            conn.executescript(fh.read())
        # 第一遍执行
        _exec_sql(conn, analysis_path)
        _exec_sql(conn, scores_path)
        count_a = conn.execute("SELECT COUNT(*) FROM dlt_analysis").fetchone()[0]
        count_s = conn.execute("SELECT COUNT(*) FROM dlt_scores").fetchone()[0]
        report["表名/语法"] = "OK（dlt_analysis/dlt_scores 均可执行）"
        report["dlt_analysis 行数"] = f"{count_a}（期望 {expect_a}）"
        report["dlt_scores 行数"] = f"{count_s}（期望 {expect_s}）"

        # JSON 可解析（抽查 payload / parts）
        payloads = [r[0] for r in conn.execute(
            "SELECT payload FROM dlt_analysis LIMIT 5")]
        parts = [r[0] for r in conn.execute(
            "SELECT parts FROM dlt_scores LIMIT 5")]
        for p in payloads + parts:
            json.loads(p)
        report["JSON 可解析"] = "OK（payload/parts 抽查通过）"

        # 字段数量与表结构
        cols_a = [r[1] for r in conn.execute("PRAGMA table_info(dlt_analysis)")]
        cols_s = [r[1] for r in conn.execute("PRAGMA table_info(dlt_scores)")]
        need_a = {"period", "kind", "metric", "version", "payload", "computed_at"}
        need_s = {"period", "kind", "num", "total", "parts", "tag",
                  "model_type", "weight_version", "computed_at"}
        report["dlt_analysis 字段"] = f"OK（{len(cols_a)} 列，包含全部必需字段）" if need_a <= set(cols_a) else f"缺失: {need_a - set(cols_a)}"
        report["dlt_scores 字段"] = f"OK（{len(cols_s)} 列，包含全部必需字段）" if need_s <= set(cols_s) else f"缺失: {need_s - set(cols_s)}"

        # 幂等：第二遍执行，行数不变
        _exec_sql(conn, analysis_path)
        _exec_sql(conn, scores_path)
        count_a2 = conn.execute("SELECT COUNT(*) FROM dlt_analysis").fetchone()[0]
        count_s2 = conn.execute("SELECT COUNT(*) FROM dlt_scores").fetchone()[0]
        report["幂等（重跑行数不变）"] = (
            f"OK（A {count_a}→{count_a2}，S {count_s}→{count_s2}）"
            if (count_a2 == count_a and count_s2 == count_s)
            else f"FAIL（A {count_a}→{count_a2}，S {count_s}→{count_s2}）"
        )

        # score TOP 对照：period=默认首个非 all 窗口、front、standard 模型
        probe_period = next((p for p in periods if p != "all"), 100)
        issues = load_issues(path=DATA_PATH)
        py_top = score_all(issues, probe_period, "front", "standard")[:10]
        py_rows = [(int(s["num"]), int(s["total"])) for s in py_top]
        sql_rows = conn.execute(
            "SELECT num, total FROM dlt_scores "
            "WHERE period=? AND kind='front' AND model_type='standard' "
            "ORDER BY total DESC, num ASC LIMIT 10",
            (0 if probe_period == "all" else int(probe_period),),
        ).fetchall()
        # Python 输出已按 total 降序（稳定排序同分保持号码升序），逐位比对
        matched = list(py_rows) == [(int(r[0]), int(r[1])) for r in sql_rows]
        report["score TOP 对照"] = (
            f"OK（period={probe_period} front standard TOP10 完全一致：{[(n, t) for n, t in py_rows]}）"
            if matched else f"FAIL\n  Python: {py_rows}\n  SQL: {sql_rows}"
        )
    finally:
        conn.close()
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="轨 B 本地闭环：Python 分析 → SQL 文件（不写 D1）")
    ap.add_argument("--periods", default=",".join(str(p) for p in DEFAULT_PERIODS),
                    help="逗号分隔窗口，如 50,100,all")
    ap.add_argument("--out-dir", default=".verify_tmp", help="SQL 输出目录")
    ap.add_argument("--no-check", action="store_true", help="跳过本地 sqlite 校验")
    args = ap.parse_args()

    periods: list = []
    for p in args.periods.split(","):
        p = p.strip()
        periods.append(p if p == "all" else int(p))

    analysis_statements, scores_statements, n_a, n_s = run_pipeline(periods)
    out_dir = os.path.join(ROOT, args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    analysis_path = os.path.join(out_dir, "analysis_inserts.sql")
    scores_path = os.path.join(out_dir, "scores_inserts.sql")
    write_sql_file(analysis_statements, analysis_path)
    write_sql_file(scores_statements, scores_path)
    print(f"[writer] dlt_analysis 语句 {len(analysis_statements)} 条 -> {analysis_path}")
    print(f"[writer] dlt_scores 语句 {len(scores_statements)} 条 -> {scores_path}")
    print("提示：默认只生成 SQL，未写 D1。执行写入（需 --remote）：")
    print(f"  wrangler d1 execute dlt-draws --remote --file={analysis_path}")
    print(f"  wrangler d1 execute dlt-draws --remote --file={scores_path}")

    if not args.no_check:
        print("\n===== SQL 检查（内存 sqlite，使用真实 DDL 建表）=====")
        report = check_sql(analysis_path, scores_path, n_a, n_s, periods)
        ok = True
        for k, v in report.items():
            flag = "✅" if not str(v).startswith("FAIL") else "❌"
            if flag == "❌":
                ok = False
            print(f"  {flag} {k}: {v}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
