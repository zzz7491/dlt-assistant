"""阶段 14 Task 6.1：D1 导入管道小规模验证（仅测试，不导入全部历史）。

读取 data/dlt_history.json 的最新 N 期（默认 10），转换为 dlt_draws 字段，
生成 INSERT OR IGNORE SQL（幂等，可重复执行）。

用法：
  python scripts/test_import_dlt.py            # 默认最新 10 期
  python scripts/test_import_dlt.py 20          # 指定期数（测试用）
然后执行：
  wrangler d1 execute dlt-draws --remote --file=.verify_tmp/import_test.sql
"""
import json
import os
import sys

SRC = "data/dlt_history.json"
OUT = ".verify_tmp/import_test.sql"
DEFAULT_N = 10


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N
    data = json.load(open(SRC, encoding="utf-8"))
    issues = data["issues"]
    if n > len(issues):
        raise SystemExit(f"请求 {n} 期，数据仅 {len(issues)} 期")
    latest = issues[-n:]  # JSON 按期号升序，末尾为最新

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lines = [f"-- 阶段14 Task6.1 测试导入（最新 {n} 期，INSERT OR IGNORE 幂等）"]
    for it in latest:
        f = it["front"]
        b = it["back"]
        assert len(f) == 5 and len(b) == 2, f"期号 {it['issue']} 号码数量异常"
        lines.append(
            "INSERT OR IGNORE INTO dlt_draws "
            "(issue, issue_num, date, front1, front2, front3, front4, front5, "
            "back1, back2, source, verified) "
            f"VALUES ('{it['issue']}', {int(it['issue'])}, '{it['date']}', "
            f"{f[0]}, {f[1]}, {f[2]}, {f[3]}, {f[4]}, {b[0]}, {b[1]}, '500', 1);"
        )
    sql = "\n".join(lines) + "\n"
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(sql)
    print(f"已生成 {OUT}：{len(latest)} 条 INSERT（{latest[0]['issue']} ~ {latest[-1]['issue']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
