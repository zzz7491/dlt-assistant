"""阶段 14 Task 6.2.2：大乐透全历史开奖数据导入 D1（07001 ~ 26092）。

- 复用 src.scraper 的请求与解析逻辑（_fetch_range / _parse_rows 口径）
- 五重校验：期号格式 / 日期合法 / 前区 1-35 / 后区 1-12 / 期号唯一
- 分批生成 INSERT OR IGNORE SQL（每批 ≤500 期，幂等可重跑）
- 写入必须：wrangler d1 execute dlt-draws --remote --file=<批次>

用法：
  python scripts/import_full_history.py
  生成批次后按提示执行 wrangler 命令（或直接用本脚本输出的命令清单）。
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402
from src.scraper import _fetch_range  # noqa: E402

START = "07001"   # 2007-05-28 上市首期
END = "26092"     # 当前最新一期（2026-08-15）
BATCH = 500
OUT_DIR = ".verify_tmp/import_full"

ISSUE_RE = re.compile(r"^\d{5}$")


def validate(issues: list[dict]) -> tuple[set, list]:
    """五重校验：期号格式 / 日期合法 / 前区 1-35 / 后区 1-12 / 期号唯一（含号码重复）。"""
    seen: set = set()
    bad: list = []
    for it in issues:
        iss = it["issue"]
        errs: list = []
        if not ISSUE_RE.fullmatch(str(iss)):
            errs.append("期号格式")
        try:
            datetime.date.fromisoformat(it["date"])
        except (ValueError, TypeError):
            errs.append("日期非法")
        f = it["front"]
        b = it["back"]
        if len(f) != 5 or not all(isinstance(x, int) and 1 <= x <= 35 for x in f):
            errs.append("前区范围")
        if len(b) != 2 or not all(isinstance(x, int) and 1 <= x <= 12 for x in b):
            errs.append("后区范围")
        if len(set(f)) != 5 or len(set(b)) != 2:
            errs.append("号码重复")
        if iss in seen:
            errs.append("期号重复")
        seen.add(iss)
        if errs:
            bad.append((iss, errs))
    return seen, bad


def main() -> int:
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
    sc = cfg["scrape"]

    print(f"[1/3] 抓取 {START} ~ {END}（复用 src.scraper._fetch_range）...")
    issues = _fetch_range(sc["base_url"], START, END, sc["timeout"], sc["user_agent"])
    issues.sort(key=lambda x: x["issue"])
    print(f"      抓到 {len(issues)} 期（{issues[0]['issue']} ~ {issues[-1]['issue']}）")

    print("[2/3] 五重校验 ...")
    seen, bad = validate(issues)
    print(f"      期号唯一数 {len(seen)}；异常 {len(bad)} 条")
    if bad:
        for iss, errs in bad[:15]:
            print(f"      ❌ {iss}: {errs}")
        return 1

    print(f"[3/3] 分批生成 SQL（每批 ≤{BATCH} 期，INSERT OR IGNORE 幂等）...")
    os.makedirs(OUT_DIR, exist_ok=True)
    files: list[str] = []
    for i in range(0, len(issues), BATCH):
        chunk = issues[i:i + BATCH]
        path = f"{OUT_DIR}/batch_{i // BATCH + 1}.sql"
        lines = [f"-- 全历史导入 batch {i // BATCH + 1}（{chunk[0]['issue']} ~ {chunk[-1]['issue']}，{len(chunk)} 期）"]
        for it in chunk:
            f = it["front"]
            b = it["back"]
            lines.append(
                "INSERT OR IGNORE INTO dlt_draws "
                "(issue, issue_num, date, front1, front2, front3, front4, front5, "
                "back1, back2, source, verified) "
                f"VALUES ('{it['issue']}', {int(it['issue'])}, '{it['date']}', "
                f"{f[0]}, {f[1]}, {f[2]}, {f[3]}, {f[4]}, {b[0]}, {b[1]}, '500', 1);"
            )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        files.append(path)
        print(f"      batch {i // BATCH + 1}: {len(chunk)} 期 -> {path}")

    print("\n执行命令（必须 --remote）：")
    for p in files:
        print(f"  wrangler d1 execute dlt-draws --remote --file={p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
