"""阶段 16.5-A-1：推荐「一期固定」D1 写入器（新增，不修改既有 Python 文件）。

机制：
  dlt_recommendations 表 UNIQUE(target_issue, strategy, idx) 唯一约束 +
  INSERT OR IGNORE ⇒ 同一「期号 + 策略 + 组」首次写入即固定，
  后续重复执行被静默忽略 —— 不覆盖、不新增重复数据，实现首页推荐一期固定。

参考 scripts/update_dlt_d1.py 风格：
  - 仅生成幂等 SQL 到 .verify_tmp/recommendations_d1.sql，不自动执行；
  - 执行由 workflow 调用 wrangler 完成（见文件末尾说明）。

读取：默认 public/data/recommendations.json（scheduler 产物经 workflow 同步后的部署数据源），
      可用 --input 指定其他 JSON（本地验证用）。

用法：
  python scripts/write_recommendations_d1.py                  # 读 public/data/recommendations.json
  python scripts/write_recommendations_d1.py --input x.json   # 指定输入（验证用）
  python scripts/write_recommendations_d1.py --check          # 本地内存 sqlite 幂等/唯一性校验（不连远端）

生成后执行（必须 --remote，由 workflow 调用）：
  wrangler d1 execute dlt-draws --remote --file=.verify_tmp/recommendations_d1.sql
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "public" / "data" / "recommendations.json"
OUT = ROOT / ".verify_tmp" / "recommendations_d1.sql"

# 与 migrations/0001_init_dlt.sql 中 dlt_recommendations 保持一致（仅用于本地校验）
_DDL = """
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


def _sql_str(s: str) -> str:
    """SQLite 字符串字面量转义（单引号翻倍）。"""
    return "'" + s.replace("'", "''") + "'"


def _validate(rec: Any) -> tuple[bool, str]:
    """校验单条推荐记录合法性，返回 (是否通过, 失败原因)。"""
    if not isinstance(rec, dict):
        return False, "记录非对象"
    if not rec.get("target_issue") or not rec.get("strategy"):
        return False, "缺少 target_issue/strategy"
    if not isinstance(rec.get("idx"), int):
        return False, "idx 非法(需整数)"
    front = rec.get("front")
    back = rec.get("back")
    if not (isinstance(front, list) and len(front) == 5
            and all(isinstance(x, int) and 1 <= x <= 35 for x in front)):
        return False, "front 非法(需5个1-35整数)"
    if not (isinstance(back, list) and len(back) == 2
            and all(isinstance(x, int) and 1 <= x <= 12 for x in back)):
        return False, "back 非法(需2个1-12整数)"
    if not rec.get("date"):
        return False, "缺少 date"
    return True, ""


def gen_sql(records: list[dict[str, Any]], path: Path) -> tuple[int, int, list[str]]:
    """生成幂等 INSERT OR IGNORE SQL。返回 (写入数量, 跳过数量, 错误信息列表)。"""
    lines = ["-- 推荐一期固定 D1 写入（幂等 INSERT OR IGNORE，可重复执行）"]
    written = 0
    skipped = 0
    errors: list[str] = []
    for i, r in enumerate(records):
        ok, msg = _validate(r)
        if not ok:
            skipped += 1
            errors.append(f"记录#{i} 跳过：{msg} -> {json.dumps(r, ensure_ascii=False)[:80]}")
            continue
        ti = str(r["target_issue"])
        st = str(r["strategy"])
        idx = int(r["idx"])
        front = json.dumps(r["front"], ensure_ascii=False)
        back = json.dumps(r["back"], ensure_ascii=False)
        date = str(r["date"])
        lines.append(
            "INSERT OR IGNORE INTO dlt_recommendations "
            "(target_issue, strategy, idx, front, back, date) "
            f"VALUES ({_sql_str(ti)}, {_sql_str(st)}, {idx}, "
            f"{_sql_str(front)}, {_sql_str(back)}, {_sql_str(date)});"
        )
        written += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written, skipped, errors


def check_idempotent(sql_path: Path) -> tuple[int, int, int]:
    """本地内存 sqlite 加载相同 DDL，重复执行两次 SQL，返回 (首次行数, 重复后行数, 唯一冲突组数)。"""
    con = sqlite3.connect(":memory:")
    con.executescript(_DDL)
    sql = sql_path.read_text(encoding="utf-8")
    con.executescript(sql)  # 第一次写入
    first = con.execute("SELECT COUNT(*) FROM dlt_recommendations").fetchone()[0]
    con.executescript(sql)  # 重复执行（模拟次日 workflow）
    second = con.execute("SELECT COUNT(*) FROM dlt_recommendations").fetchone()[0]
    dup = con.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT target_issue, strategy, idx FROM dlt_recommendations "
        "GROUP BY target_issue, strategy, idx HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    con.close()
    return first, second, dup


def main() -> int:
    args = sys.argv[1:]
    input_path = DEFAULT_IN
    do_check = "--check" in args
    if "--input" in args:
        input_path = Path(args[args.index("--input") + 1])

    if not input_path.exists():
        print(f"⚠️ 输入文件不存在：{input_path}")
        return 1

    records = json.loads(input_path.read_text(encoding="utf-8"))
    written, skipped, errors = gen_sql(records, OUT)

    print(f"✅ 生成 SQL -> {OUT}")
    print(f"写入数量（有效 INSERT 语句）: {written}")
    print(f"跳过数量（异常记录）: {skipped}")
    for e in errors:
        print(f"  ⚠️ {e}")
    print("执行：")
    print(f"  wrangler d1 execute dlt-draws --remote --file={OUT}")

    if do_check:
        first, second, dup = check_idempotent(OUT)
        print(f"[check] 首次写入行数={first}，重复写入后行数={second}")
        print(f"[check] 重复执行行数变化={second - first}（应为 0）")
        print(f"[check] 唯一键(target_issue,strategy,idx)冲突组数={dup}（应为 0）")
        if written != first:
            print(f"[check] 输入 {written} 条中 {written - first} 条因唯一约束合并（首写即定，不覆盖）")
        ok = first == second and dup == 0
        print("✅ 本地幂等/唯一性校验通过" if ok else "❌ 校验失败")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
