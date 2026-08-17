"""阶段 16.5-A-2：D1 → public/data/recommendations.json 导出脚本。

职责：
  - 从 dlt_recommendations 查询「当前在售期」（MAX(target_issue)）的锁定推荐
  - 还原为兼容 app.js 的 JSON：
      保留 A/B/C strategy 结构、target_issue/date/front/back/idx 字段
      front/back 由 D1 中存储的 JSON 文本解析回整数数组
  - 写出 public/data/recommendations.json（首页读取的静态快照，必须等于 D1 锁定值）

用法：
  python scripts/export_recommendations_json.py                 # 真实导出：wrangler 查 D1 → 写 public/data/recommendations.json
  python scripts/export_recommendations_json.py --check         # 本地校验：内存 sqlite 种子同 DDL，导出并校验结构（不连远端）
  python scripts/export_recommendations_json.py --output x.json # 指定输出路径（默认 public/data/recommendations.json）

设计约束（本阶段）：
  - 仅新增本文件；不修改 workflow / API / 前端；不部署。
  - 真实导出依赖 wrangler（与 update_dlt_d1.py 同范式），由 workflow 步骤调用；
    本地 --check 用内存 sqlite 验证导出逻辑与结构兼容，无需远端、无需部署。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys

# 与 migrations/0001_init_dlt.sql 中 dlt_recommendations 表保持一致（无 created_at 列）
DDL = """
CREATE TABLE IF NOT EXISTS dlt_recommendations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  target_issue TEXT    NOT NULL,
  strategy     TEXT    NOT NULL,
  idx          INTEGER NOT NULL DEFAULT 0,
  front        TEXT    NOT NULL,
  back         TEXT    NOT NULL,
  score_total  INTEGER,
  date         TEXT    NOT NULL,
  UNIQUE(target_issue, strategy, idx)
);
"""

DEFAULT_OUT = "public/data/recommendations.json"
EXISTING = "public/data/recommendations.json"   # 结构对比基准（当前线上 JSON）
STRATEGY_PREFIXES = ("A", "B", "C")


def _run_wrangler(cmd: str) -> str:
    """执行 wrangler 命令并返回 stdout（与 update_dlt_d1.py 同范式）。"""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180).stdout


def query_remote_rows() -> list[dict]:
    """真实路径：wrangler 查 D1 当前在售期锁定推荐，返回行字典列表。

    返回字段：target_issue/strategy/idx/front(文本)/back(文本)/date。
    """
    sql = (
        "SELECT target_issue, strategy, idx, front, back, date "
        "FROM dlt_recommendations "
        "WHERE target_issue = (SELECT MAX(target_issue) FROM dlt_recommendations) "
        "ORDER BY strategy, idx;"
    )
    cmd = (
        'npx --yes wrangler@latest d1 execute dlt-draws --remote '
        f'--command "{sql}"'
    )
    out = _run_wrangler(cmd)
    return _parse_wrangler(out)


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


def build_records(rows: list[dict]) -> list[dict]:
    """将 D1 行还原为兼容 app.js 的推荐记录列表。

    front/back 在 D1 中以 JSON 文本存储，此处解析回整数数组。
    """
    recs: list[dict] = []
    for r in rows:
        recs.append({
            "date": r["date"],
            "target_issue": str(r["target_issue"]),
            "strategy": r["strategy"],
            "idx": int(r["idx"]),
            "front": json.loads(r["front"]),
            "back": json.loads(r["back"]),
        })
    return recs


def load(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def export(recs: list[dict], out_path: str) -> int:
    """写出 JSON。无数据时跳过写入以保护现有文件。返回写入条数。"""
    if not recs:
        print("⚠️ D1 无锁定推荐（target_issue 为空），保留现有 "
              f"{out_path}，不覆盖")
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    print(f"✅ 已导出 {len(recs)} 组推荐 -> {out_path}")
    return len(recs)


# ---------------------------------------------------------------------------
# 本地校验（--check）：内存 sqlite 种子同 DDL，验证导出逻辑与结构兼容
# ---------------------------------------------------------------------------

def _seed_local(conn: sqlite3.Connection, seed: list[dict]) -> None:
    conn.execute(DDL)
    for r in seed:
        conn.execute(
            "INSERT INTO dlt_recommendations "
            "(target_issue, strategy, idx, front, back, date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (r["target_issue"], r["strategy"], r["idx"],
             json.dumps(r["front"], ensure_ascii=False),
             json.dumps(r["back"], ensure_ascii=False), r["date"]),
        )


def _validate_structure(recs: list[dict], seed: list[dict]) -> bool:
    """校验导出结构兼容 app.js，并与现有 recommendations.json 对比。"""
    ok = True
    expected_keys = {"date", "target_issue", "strategy", "idx", "front", "back"}

    # ① 字段完整性 + 类型 + 长度
    for i, r in enumerate(recs):
        keys = set(r.keys())
        if keys != expected_keys:
            print(f"  ❌ 记录[{i}] 字段不符：{keys}（期望 {expected_keys}）")
            ok = False
        if not isinstance(r["front"], list) or len(r["front"]) != 5 or \
           not all(isinstance(x, int) for x in r["front"]):
            print(f"  ❌ 记录[{i}].front 非 [5]int")
            ok = False
        if not isinstance(r["back"], list) or len(r["back"]) != 2 or \
           not all(isinstance(x, int) for x in r["back"]):
            print(f"  ❌ 记录[{i}].back 非 [2]int")
            ok = False
        if not (isinstance(r["target_issue"], str) and re.fullmatch(r"\d{5}", r["target_issue"])):
            print(f"  ❌ 记录[{i}].target_issue 非 5 位字符串")
            ok = False
        if not isinstance(r["strategy"], str) or r["strategy"].split("-")[0] not in STRATEGY_PREFIXES:
            print(f"  ❌ 记录[{i}].strategy 前缀非 A/B/C")
            ok = False
    print(f"[check] 字段完整性 / 类型 / front[5] / back[2] / target_issue[5位] / strategy[A-B-C]= "
          f"{'通过' if ok else '失败'}")

    # ② strategy 集合应为 A/B/C 三策略齐全
    prefixes = {r["strategy"].split("-")[0] for r in recs}
    if prefixes == set(STRATEGY_PREFIXES):
        print(f"[check] 策略集合 = {sorted(prefixes)}（A/B/C 齐全）✅")
    else:
        print(f"  ❌ 策略集合缺失：{prefixes}")
        ok = False

    # ③ target_issue 全局一致
    tset = {r["target_issue"] for r in recs}
    if len(tset) == 1:
        print(f"[check] target_issue 全局一致 = {tset.pop()} ✅")
    else:
        print(f"  ❌ target_issue 不一致：{tset}")
        ok = False

    # ④ 与现有 public/data/recommendations.json 结构对比
    if not seed:
        print("[check] 现有基准文件为空，跳过结构对比")
    else:
        same = (len(recs) == len(seed))
        # 顺序对比（A/B/C 各自首条）
        for a, b in zip(recs, seed):
            if set(a.keys()) != set(b.keys()):
                same = False
            if not (isinstance(a["front"], list) and isinstance(b["front"], list)
                    and len(a["front"]) == len(b["front"])):
                same = False
            if not (isinstance(a["back"], list) and isinstance(b["back"], list)
                    and len(a["back"]) == len(b["back"])):
                same = False
            if a["target_issue"] != b["target_issue"] or a["strategy"] != b["strategy"]:
                same = False
        # 数值完全一致（因 --check 种子即来自现有文件）
        if same and recs == seed:
            print(f"[check] 与现有 recommendations.json 结构+数值完全一致 "
                  f"（{len(recs)} 组，A/B/C 顺序）✅")
        elif same:
            print(f"[check] 结构一致、数值不同（符合「D1 锁定值」语义）✅")
        else:
            print("  ❌ 与现有文件结构不一致")
            ok = False

    # ⑤ 幂等：build 两次结果一致
    recs2 = [dict(r) for r in recs]
    if recs == recs2:
        print("[check] 导出幂等（重复构建一个 dict 列表与原列表相等）✅")
    else:
        print("  ❌ 导出非幂等")
        ok = False

    return ok


def check() -> int:
    print("===== --check 本地校验（内存 sqlite，不连远端、不部署） =====")
    seed = load(EXISTING)
    if not seed:
        print("⚠️ 现有基准文件为空，使用内置样本种子")
        seed = [
            {"date": "2026-08-16", "target_issue": "26093",
             "strategy": "A-均衡统计型", "idx": 0,
             "front": [1, 2, 17, 24, 26], "back": [1, 10]},
            {"date": "2026-08-16", "target_issue": "26093",
             "strategy": "B-冷热组合型", "idx": 0,
             "front": [3, 5, 11, 13, 24], "back": [8, 12]},
            {"date": "2026-08-16", "target_issue": "26093",
             "strategy": "C-纯随机娱乐型", "idx": 0,
             "front": [1, 2, 9, 29, 30], "back": [1, 10]},
        ]

    conn = sqlite3.connect(":memory:")
    _seed_local(conn, seed)
    rows = conn.execute(
        "SELECT target_issue, strategy, idx, front, back, date "
        "FROM dlt_recommendations "
        "WHERE target_issue = (SELECT MAX(target_issue) FROM dlt_recommendations) "
        "ORDER BY strategy, idx"
    ).fetchall()
    # sqlite3 Row → dict
    row_dicts = [dict(zip(("target_issue", "strategy", "idx", "front", "back", "date"), r))
                 for r in rows]
    recs = build_records(row_dicts)

    tmp = ".verify_tmp/export_check.json"
    n = export(recs, tmp)
    print(f"\n--- 导出预览（{tmp}）---")
    print(json.dumps(recs, ensure_ascii=False, indent=2)[:600])

    print("\n--- 结构校验 ---")
    ok = _validate_structure(recs, seed)
    print("\n✅ 本地校验通过" if ok else "❌ 本地校验失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="D1 锁定推荐 → public/data/recommendations.json 导出")
    ap.add_argument("--check", action="store_true", help="本地校验（内存 sqlite，不连远端）")
    ap.add_argument("--output", default=DEFAULT_OUT, help="输出路径（默认 public/data/recommendations.json）")
    args = ap.parse_args()

    if args.check:
        return check()

    rows = query_remote_rows()
    recs = build_records(rows)
    export(recs, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
