"""一次性清理：删除全部「C-纯随机娱乐型」历史推荐，并为当前目标期回填 C-AI。

用户指令（2026-10-20）：随机推荐全部删除（机选功能除外，与本脚本无关）。
本脚本做三件事（同一批次内按顺序）：
  1. 当前目标期回填：复用 oneoff_replace_c_ai 的逻辑，对 5 个当前目标期
     （ssq 26120 / fc3d 2026279 / pl3 26279 / pl5 26279 / dlt 26120）
     先生成 C-AI智能型 并替换其随机 C 行；AI 失败则该彩种保留旧行并跳过
     第 2 步中对该表的删除（绝不把当前期 C 弄丢，失败情况会打印告警）。
  2. 全量删除：其余 4 个（或全部成功回填后的 5 个）表里所有
     strategy='C-纯随机娱乐型' 的行，删除前先 SELECT * 打印到日志留档。
  3. 复查：打印每表残留随机 C 行数（应为 0）与当前目标期策略列表。

运行环境：仓库根目录；需 CLOUDFLARE_API_TOKEN（wrangler）与
DLT_AI_API_KEY（或 OPENROUTER_API_KEY）。默认 dry-run 只打印计划 SQL；
--apply 才执行。幂等：重复跑只处理剩余行。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

OLD = "C-纯随机娱乐型"
TABLES = [
    "ssq_recommendations",
    "fc3d_recommendations",
    "pl3_recommendations",
    "pl5_recommendations",
    "dlt_recommendations",
]


def _load_replace_module():
    path = os.path.join(ROOT, "scripts", "oneoff_replace_c_ai.py")
    spec = importlib.util.spec_from_file_location("oneoff_replace_c_ai", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wrangler(mod, sql: str, as_file: bool = False) -> str:
    return mod._wrangler(sql, as_file=as_file)


def _count_old(mod, table: str) -> int:
    out = _wrangler(mod, f"SELECT COUNT(*) AS n FROM {table} WHERE strategy='{OLD}';")
    import re

    m = re.search(r'"n":\s*(\d+)', out)
    return int(m.group(1)) if m else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    mod = _load_replace_module()

    # 第 1 步：当前目标期回填 AI（复用 replace 的逐彩种 SQL 构造）
    backfill_sql = []
    failed_games = []
    for game in mod.GAMES:
        try:
            sql = mod._build_four_game_sql(game)
            if sql:
                backfill_sql.append(sql)
        except Exception as e:  # 单彩种失败不阻断其余
            print(f"[{game['id']}] 回填准备失败：{type(e).__name__}: {e}")
            failed_games.append(game["table"])
    try:
        sql = mod._build_dlt_sql()
        if sql:
            backfill_sql.append(sql)
    except Exception as e:
        print(f"[dlt] 回填准备失败：{type(e).__name__}: {e}")
        failed_games.append(mod.DLT_TABLE)

    # 第 2 步：全量删除（跳过回填失败的表，保住当前期）
    delete_tables = [t for t in TABLES if t not in failed_games]
    if failed_games:
        print(f"⚠️ 以下表回填失败，本次不删其随机 C（保住当前期，事后重跑）：{failed_games}")

    if not args.apply:
        print("===== DRY-RUN =====")
        print(f"回填 SQL {len(backfill_sql)} 段；将删除随机 C 的表：{delete_tables}")
        for t in delete_tables:
            print(f"[{t}] 现有随机 C 行数：{_count_old(mod, t)}")
        if backfill_sql:
            print("\n".join(backfill_sql))
        print("确认无误后加 --apply 重新运行。")
        return 0

    if backfill_sql:
        _wrangler(mod, "\n".join(backfill_sql) + "\n", as_file=True)
        print("回填完成。")

    for t in delete_tables:
        print(f"===== [{t}] 删除前留档（strategy='{OLD}' 全部行）=====")
        print(_wrangler(mod, f"SELECT * FROM {t} WHERE strategy='{OLD}';"))
        _wrangler(mod, f"DELETE FROM {t} WHERE strategy='{OLD}';")
        print(f"[{t}] 删除后残留随机 C 行数：{_count_old(mod, t)}")

    print("===== 复查：当前目标期策略列表 =====")
    ok = True
    for game in mod.GAMES:
        ss = mod._existing_strategies(game["table"], game["target_issue"])
        good = OLD not in ss
        ok = ok and good
        print(f"[{game['id']}] {game['target_issue']}: {ss} {'✅' if good else '❌'}")
    ss = mod._existing_strategies(mod.DLT_TABLE, mod.DLT_TARGET)
    good = OLD not in ss
    ok = ok and good
    print(f"[dlt] {mod.DLT_TARGET}: {ss} {'✅' if good else '❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
