"""策略长期命中统计导出：D1 → public/data/strategy_reviews.json。

职责：
  - 从 dlt_draws（全历史开奖）与 dlt_recommendations（全历史锁定推荐）
    按 target_issue = issue 关联，逐策略聚合长期命中统计：
    累计复盘期数 / 平均每期前区命中 / 平均每期后区命中 /
    前区命中分布 / 最近 10 期逐期明细（样本不足 10 期时标注）。
  - 同一 (target_issue, strategy) 的多 idx 行先按期取均值再参与聚合。
  - 历史「C-纯随机娱乐型」记录已按用户指令（2026-10-20）删除；
    计算中对 strategy 含「纯随机」的行做防御性跳过，绝不统计、不展示。

用法：
  python scripts/export_strategy_reviews.py                 # 真实导出：wrangler 查 D1 → 写 public/data/strategy_reviews.json
  python scripts/export_strategy_reviews.py --check        # 本地校验：内存 sqlite 种子数据（含一行纯随机残留以验证跳过）
  python scripts/export_strategy_reviews.py --output x.json # 指定输出路径

部署：
  - 在 dlt-analysis.yml 里 export_recommendations_json.py 步骤之后加一步：
      python scripts/export_strategy_reviews.py
    （同一步已有 CLOUDFLARE_API_TOKEN 环境，复用即可）
  - 首页 app.js 会 fetch ./data/strategy_reviews.json（无文件时降级显示「积累中」）
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sqlite3
import subprocess
import sys

DEFAULT_OUT = "public/data/strategy_reviews.json"

DISCLAIMER = "命中统计仅为历史娱乐回顾；彩票开奖为独立随机事件，不代表任何预测依据。"
MAIN_LABEL = "前区命中"
SUB_LABEL = "后区命中"
MAIN_MAX = 5


def _run_wrangler(cmd: str) -> str:
    """执行 wrangler 命令并返回 stdout（与 update_dlt_d1.py 同范式）。"""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180).stdout


def _parse_wrangler(out: str) -> list[dict]:
    """解析 wrangler d1 execute --command 的 JSON 输出，提取行列表。"""
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", out, re.S)
        if not m:
            return []
        data = json.loads(m.group(0))
    rows: list[dict] = []
    statements = data if isinstance(data, list) else [data]
    for stmt in statements:
        if isinstance(stmt, dict):
            rows.extend(stmt.get("results", []))
    return rows


def query_remote() -> tuple[list[dict], list[dict]]:
    """真实路径：wrangler 查 D1 全量开奖 + 全量锁定推荐。"""
    draws_sql = (
        "SELECT issue, date, front1, front2, front3, front4, front5, back1, back2 "
        "FROM dlt_draws ORDER BY issue_num ASC;"
    )
    recs_sql = (
        "SELECT target_issue, strategy, idx, front, back, date "
        "FROM dlt_recommendations ORDER BY target_issue ASC, strategy, idx;"
    )
    draws = _parse_wrangler(_run_wrangler(
        'npx --yes wrangler@latest d1 execute dlt-draws --remote '
        f'--command "{draws_sql}"'))
    recs = _parse_wrangler(_run_wrangler(
        'npx --yes wrangler@latest d1 execute dlt-draws --remote '
        f'--command "{recs_sql}"'))
    return draws, recs


def _as_int_list(v) -> list[int]:
    if isinstance(v, list):
        return [int(x) for x in v]
    if isinstance(v, str):
        return [int(x) for x in json.loads(v)]
    return []


def aggregate(draws: list[dict], recs: list[dict]) -> dict:
    """纯函数：开奖行 × 推荐行 → 策略长期命中统计。"""
    by_issue: dict[str, dict] = {}
    for d in draws:
        issue = str(d["issue"])
        by_issue[issue] = {
            "front": {int(d[f"front{i}"]) for i in range(1, 6)},
            "back": {int(d[f"back{i}"]) for i in range(1, 3)},
        }

    # (target_issue, strategy) → idx 列表的命中（多 idx 先按期取均值）
    per_issue: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for r in recs:
        strategy = str(r.get("strategy") or "")
        if not strategy or "纯随机" in strategy:
            continue  # 历史纯随机记录已删除，防御性跳过
        issue = str(r["target_issue"])
        draw = by_issue.get(issue)
        if not draw:
            continue  # 未开奖（未来目标期），不参与复盘
        front = set(_as_int_list(r["front"]))
        back = set(_as_int_list(r["back"]))
        key = (issue, strategy)
        per_issue.setdefault(key, []).append(
            (float(len(front & draw["front"])), float(len(back & draw["back"])))
        )

    # 按策略聚合：先按期取均值（多 idx），再跨期聚合
    groups: dict[str, list[tuple[str, float, float]]] = {}
    for (issue, strategy), hits in per_issue.items():
        m = sum(h[0] for h in hits) / len(hits)
        s = sum(h[1] for h in hits) / len(hits)
        groups.setdefault(strategy, []).append((issue, round(m, 2), round(s, 2)))

    strategies = []
    for strategy in sorted(groups):
        rows = sorted(groups[strategy], key=lambda x: x[0])
        periods = len(rows)
        avg_main = round(sum(x[1] for x in rows) / periods, 2) if periods else 0.0
        avg_sub = round(sum(x[2] for x in rows) / periods, 2) if periods else 0.0
        dist: dict[str, int] = {}
        for _, m, _ in rows:
            k = str(int(round(m)))
            dist[k] = dist.get(k, 0) + 1
        recent = [{"issue": x[0], "hits": x[1], "hits_sub": x[2]}
                  for x in rows[-10:]][::-1]
        strategies.append({
            "strategy": strategy,
            "periods": periods,
            "avg_hits": avg_main,
            "avg_hits_sub": avg_sub,
            "dist": dist,
            "recent": recent,
            "sample_warning": periods < 10,
        })
    strategies.sort(key=lambda s: (-s["avg_hits"], s["strategy"]))
    return {
        "strategies": strategies,
        "hit_labels": {"main": MAIN_LABEL, "sub": SUB_LABEL, "main_max": MAIN_MAX},
        "disclaimer": DISCLAIMER,
    }


def export(payload: dict, out_path: str) -> bool:
    """写出 JSON；无策略数据时跳过写入以保护现有文件。返回是否写入。"""
    if not payload.get("strategies"):
        print("⚠️ 无可复盘的策略数据，保留现有文件")
        return False
    payload = dict(payload)
    payload["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"✅ 已写出 {out_path}（{len(payload['strategies'])} 个策略）")
    return True


def _seed_local(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE dlt_draws (
        issue TEXT UNIQUE, issue_num INTEGER UNIQUE, date TEXT,
        front1 INT, front2 INT, front3 INT, front4 INT, front5 INT,
        back1 INT, back2 INT)""")
    conn.execute("""CREATE TABLE dlt_recommendations (
        target_issue TEXT, strategy TEXT, idx INT, front TEXT, back TEXT, date TEXT,
        UNIQUE(target_issue, strategy, idx))""")
    # 3 期开奖：A 每期中前区 3 个，B 每期中 1 个，C-AI智能型 每期中 2 个，
    # C-纯随机娱乐型（残留行）必须被跳过。
    draws = [
        ("26090", 26090, "2026-08-08", 3, 6, 20, 24, 32, 4, 7),
        ("26091", 26091, "2026-08-10", 1, 9, 15, 22, 30, 2, 11),
        ("26092", 26092, "2026-08-12", 5, 12, 18, 27, 33, 6, 9),
    ]
    for d in draws:
        conn.execute("INSERT INTO dlt_draws VALUES (?,?,?,?,?,?,?,?,?,?)", d)
    recs = [
        ("26090", "A-均衡统计型", 0, "[3,6,20,1,2]", "[4,8]", "2026-08-07"),   # 前3 后1
        ("26091", "A-均衡统计型", 0, "[1,9,15,2,3]", "[2,5]", "2026-08-09"),   # 前3 后1
        ("26092", "A-均衡统计型", 0, "[5,12,18,1,2]", "[6,7]", "2026-08-11"),  # 前3 后1
        ("26090", "B-冷热组合型", 0, "[3,1,2,4,5]", "[1,2]", "2026-08-07"),    # 前1 后0
        ("26091", "B-冷热组合型", 0, "[1,2,3,4,5]", "[3,4]", "2026-08-09"),    # 前1 后0
        ("26092", "B-冷热组合型", 0, "[5,1,2,3,4]", "[1,2]", "2026-08-11"),    # 前1 后0
        ("26090", "C-AI智能型", 0, "[3,6,1,2,4]", "[4,1]", "2026-08-07"),      # 前2 后1
        ("26091", "C-AI智能型", 0, "[1,9,2,3,4]", "[2,3]", "2026-08-09"),      # 前2 后1
        ("26092", "C-AI智能型", 0, "[5,12,1,2,3]", "[6,1]", "2026-08-11"),     # 前2 后1
        ("26090", "C-纯随机娱乐型", 0, "[3,6,20,24,32]", "[4,7]", "2026-08-07"),  # 全中但必须被跳过
    ]
    for r in recs:
        conn.execute("INSERT INTO dlt_recommendations VALUES (?,?,?,?,?,?)", r)


def check() -> int:
    """本地校验：内存 sqlite 种子数据，不连远端。"""
    conn = sqlite3.connect(":memory:")
    _seed_local(conn)
    draws = [dict(zip(("issue", "issue_num", "date", "front1", "front2", "front3",
                       "front4", "front5", "back1", "back2"), r))
             for r in conn.execute("SELECT * FROM dlt_draws ORDER BY issue_num")]
    recs = [dict(zip(("target_issue", "strategy", "idx", "front", "back", "date"), r))
            for r in conn.execute("SELECT * FROM dlt_recommendations")]
    payload = aggregate(draws, recs)

    ok = True

    def expect(cond: bool, msg: str) -> None:
        nonlocal ok
        print(("✅ " if cond else "❌ ") + msg)
        if not cond:
            ok = False

    names = [s["strategy"] for s in payload["strategies"]]
    expect("C-纯随机娱乐型" not in names, "纯随机残留行被跳过（不统计、不展示）")
    expect(len(names) == 3, f"三个策略全部在列（得 {len(names)}）")
    by = {s["strategy"]: s for s in payload["strategies"]}
    expect(by["A-均衡统计型"]["periods"] == 3, "A 累计 3 期")
    expect(by["A-均衡统计型"]["avg_hits"] == 3.0, "A 平均前区命中 3.0")
    expect(by["A-均衡统计型"]["avg_hits_sub"] == 1.0, "A 平均后区命中 1.0")
    expect(by["B-冷热组合型"]["avg_hits"] == 1.0, "B 平均前区命中 1.0")
    expect(by["C-AI智能型"]["avg_hits"] == 2.0, "C-AI 平均前区命中 2.0")
    expect(by["A-均衡统计型"]["sample_warning"] is True, "3 期 < 10 期 → 样本不足标注")
    expect(by["A-均衡统计型"]["dist"] == {"3": 3}, "A 前区命中分布 {3: 3}")
    expect(len(by["A-均衡统计型"]["recent"]) == 3, "A 最近明细 3 条")
    expect(by["A-均衡统计型"]["recent"][0]["issue"] == "26092", "最近明细按期号倒序")
    # 排序：avg_hits 降序 → A(3.0) > C-AI(2.0) > B(1.0)
    expect(names == ["A-均衡统计型", "C-AI智能型", "B-冷热组合型"],
           f"按平均命中降序排列（得 {names}）")
    expect(payload["hit_labels"]["main_max"] == 5, "前区满分 5")
    print("\n✅ 本地校验通过" if ok else "\n❌ 本地校验失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="D1 开奖×锁定推荐 → public/data/strategy_reviews.json")
    ap.add_argument("--check", action="store_true", help="本地校验（内存 sqlite，不连远端）")
    ap.add_argument("--output", default=DEFAULT_OUT, help="输出路径")
    args = ap.parse_args()

    if args.check:
        return check()

    draws, recs = query_remote()
    if not draws or not recs:
        print("⚠️ D1 查询无数据，保留现有文件")
        return 0
    payload = aggregate(draws, recs)
    export(payload, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
