"""一次性替换：把已首写锁定的纯随机 C 推荐替换为 C-AI智能型。

背景（2026-10-20）：四彩种 + 大乐透的 C 策略由纯随机改为 LLM 出号。
改码上线前，今晚目标期的 C 行已按纯随机生成并首写锁定：
- 双色球 ssq_recommendations：target_issue='26120'
- 福彩3D fc3d_recommendations：target_issue='2026279'
- 排列三 pl3_recommendations：target_issue='26279'
- 排列五 pl5_recommendations：target_issue='26279'
- 大乐透 dlt_recommendations：target_issue='26120'

本脚本只动这 5 行：DELETE 旧 'C-纯随机娱乐型' 行 + INSERT 新
'C-AI智能型' 行（同一 .sql 批次，D1 原子执行）。幂等：
- 若 'C-AI智能型' 行已存在 → 跳过该彩种；
- 若 AI 出号失败 → 不删旧行，跳过（绝不留空）；
- 默认 dry-run 只打印 SQL；加 --apply 才真正执行。

运行环境：仓库根目录；需 CLOUDFLARE_API_TOKEN（wrangler）
与 DLT_AI_API_KEY（或 OPENROUTER_API_KEY，ai_pick 用）。

用法：
  python scripts/oneoff_replace_c_ai.py            # dry-run，打印将要执行的 SQL
  python scripts/oneoff_replace_c_ai.py --apply   # 真正执行并复查
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

BJ = datetime.timezone(datetime.timedelta(hours=8))

GAMES = [
    {
        "id": "ssq",
        "table": "ssq_recommendations",
        "target_issue": "26120",
        "history_json": "data/ssq_history.json",
        "stats_mod": "src.ssq.stats",
        "pick_cols": ("red", "blue"),
    },
    {
        "id": "fc3d",
        "table": "fc3d_recommendations",
        "target_issue": "2026279",
        "history_json": "data/fc3d_history.json",
        "stats_mod": "src.fc3d.stats",
        "pick_cols": ("digits",),
    },
    {
        "id": "pl3",
        "table": "pl3_recommendations",
        "target_issue": "26279",
        "history_json": "data/pl3_history.json",
        "stats_mod": "src.pl3.stats",
        "pick_cols": ("digits",),
    },
    {
        "id": "pl5",
        "table": "pl5_recommendations",
        "target_issue": "26279",
        "history_json": "data/pl5_history.json",
        "stats_mod": "src.pl5.stats",
        "pick_cols": ("digits",),
    },
]

DLT_TARGET = "26120"
DLT_TABLE = "dlt_recommendations"


def _sql_text(value) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "'" + value.replace("'", "''") + "'"


def _wrangler(sql: str, as_file: bool = False) -> str:
    if as_file:
        path = os.path.join(ROOT, ".verify_tmp", "oneoff_replace_c_ai.sql")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(sql)
        cmd = (
            "npx --yes wrangler@latest d1 execute dlt-draws --remote "
            f"--file={path}"
        )
    else:
        cmd = (
            "npx --yes wrangler@latest d1 execute dlt-draws --remote "
            f'--command "{sql}"'
        )
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler 执行失败：{out[:500]}")
    return proc.stdout or ""


def _existing_strategies(table: str, target_issue: str) -> list[str]:
    out = _wrangler(
        f"SELECT strategy FROM {table} WHERE target_issue='{target_issue}';"
    )
    return [m for m in
            __import__("re").findall(r'"strategy":\s*"([^"]+)"', out)]


def _load_history(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["issues"]


def _build_four_game_sql(game: dict) -> str | None:
    import importlib

    table, target = game["table"], game["target_issue"]
    strategies = _existing_strategies(table, target)
    if "C-AI智能型" in strategies:
        print(f"[{game['id']}] 已有 C-AI智能型 行，跳过")
        return None
    if "C-纯随机娱乐型" not in strategies:
        print(f"[{game['id']}] 未找到待替换的 C-纯随机娱乐型 行（现有：{strategies}），跳过")
        return None
    stats = importlib.import_module(game["stats_mod"])
    history = _load_history(game["history_json"])
    expect = stats.next_target(history[-1])
    assert expect["issue"] == target, (
        f"[{game['id']}] 目标期号不符：history 下一期={expect['issue']}，"
        f"期望={target}，中止以防误替换"
    )
    pick = stats.generate_c_ai(target, history)
    if pick is None:
        print(f"[{game['id']}] AI 出号失败（无密钥/调用失败），保留旧行，跳过")
        return None
    today = datetime.datetime.now(BJ).date().isoformat()
    cols = ["target_issue", "target_date", "strategy", "date"]
    vals = [_sql_text(target), _sql_text(expect["date"]),
            _sql_text("C-AI智能型"), _sql_text(today)]
    if game["pick_cols"] == ("red", "blue"):
        cols[3:3] = ["red", "blue"]
        vals[3:3] = [_sql_text(pick["red"]), str(int(pick["blue"]))]
    else:
        cols[3:3] = ["digits"]
        vals[3:3] = [_sql_text(pick["digits"])]
    print(f"[{game['id']}] AI 出号成功：{pick}")
    return (
        f"-- {game['id']} {target}：替换纯随机 C 为 C-AI智能型\n"
        f"DELETE FROM {table} WHERE target_issue={_sql_text(target)} "
        f"AND strategy='C-纯随机娱乐型';\n"
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(vals)});"
    )


def _build_dlt_sql() -> str | None:
    import yaml

    strategies = _existing_strategies(DLT_TABLE, DLT_TARGET)
    if "C-AI智能型" in strategies:
        print("[dlt] 已有 C-AI智能型 行，跳过")
        return None
    if "C-纯随机娱乐型" not in strategies:
        print(f"[dlt] 未找到待替换的 C-纯随机娱乐型 行（现有：{strategies}），跳过")
        return None
    from src.analyzer import analyze
    from src import recommender

    with open(os.path.join(ROOT, "public", "data", "dlt_history.json"), encoding="utf-8") as fh:
        issues = json.load(fh)["issues"]
    cfg = yaml.safe_load(
        open(os.path.join(ROOT, "config", "settings.yaml"), encoding="utf-8")
    )
    analysis = analyze(issues, cfg)
    combo = recommender._strategy_ai(
        analysis, cfg,
        recent_issues=[
            {"issue": it.get("issue"), "front": it.get("front"), "back": it.get("back")}
            for it in issues[-10:]
        ],
        target_issue=DLT_TARGET,
    )
    if combo is None:
        print("[dlt] AI 出号失败（无密钥/调用失败），保留旧行，跳过")
        return None
    from src.recommendations import build_records

    recs = build_records([combo], DLT_TARGET, "C-AI智能型")
    r = recs[0]
    print(f"[dlt] AI 出号成功：front={r['front']} back={r['back']}")
    return (
        f"-- dlt {DLT_TARGET}：替换纯随机 C 为 C-AI智能型\n"
        f"DELETE FROM {DLT_TABLE} WHERE target_issue={_sql_text(DLT_TARGET)} "
        f"AND strategy='C-纯随机娱乐型';\n"
        f"INSERT INTO {DLT_TABLE} (target_issue, strategy, idx, front, back, date) "
        f"VALUES ({_sql_text(r['target_issue'])}, {_sql_text(r['strategy'])}, "
        f"{int(r['idx'])}, {_sql_text(r['front'])}, {_sql_text(r['back'])}, "
        f"{_sql_text(r['date'])});"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行（默认只 dry-run 打印 SQL）")
    args = ap.parse_args()

    batches = []
    for game in GAMES:
        try:
            sql = _build_four_game_sql(game)
            if sql:
                batches.append(sql)
        except Exception as e:
            print(f"[{game['id']}] 准备失败：{type(e).__name__}: {e}，跳过")
    try:
        sql = _build_dlt_sql()
        if sql:
            batches.append(sql)
    except Exception as e:
        print(f"[dlt] 准备失败：{type(e).__name__}: {e}，跳过")

    if not batches:
        print("没有需要替换的行（全部已是 AI 版或被跳过）。")
        return 0
    full = "\n".join(batches) + "\n"
    if not args.apply:
        print("===== DRY-RUN：将要执行的 SQL（未执行）=====")
        print(full)
        print("确认无误后加 --apply 重新运行。")
        return 0
    _wrangler(full, as_file=True)
    print("已执行，复查：")
    ok = True
    for game in GAMES:
        ss = _existing_strategies(game["table"], game["target_issue"])
        good = "C-AI智能型" in ss and "C-纯随机娱乐型" not in ss
        ok = ok and good
        print(f"[{game['id']}] {game['table']} {game['target_issue']}: {ss} "
              f"{'✅' if good else '❌'}")
    ss = _existing_strategies(DLT_TABLE, DLT_TARGET)
    good = "C-AI智能型" in ss and "C-纯随机娱乐型" not in ss
    ok = ok and good
    print(f"[dlt] {DLT_TABLE} {DLT_TARGET}: {ss} {'✅' if good else '❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
