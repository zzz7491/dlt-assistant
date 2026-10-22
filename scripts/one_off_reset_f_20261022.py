"""一次性重置二号（2026-10-22 用户指令：F-综合AI型上线，推翻本期、按新机制整期重出）。

仅当两个条件同时满足时才动作，过期/错流自动失效：
  1. 当前 UTC 时间早于 2026-10-22 13:00（北京时间 21:00，今晚开奖前）；
  2. 运行环境 GITHUB_WORKFLOW == 大乐透AI娱乐分析（足彩链不会误触）。

动作：
  - 往 update_d1.sql 追加 DELETE（同批执行、位于各钩子重插之前）：
    大乐透 26121 的 dlt_recommendations；四个数字彩当前期的
    recommendations/plans/analysis。
  - 工作树内清掉大乐透 26121 的发布快照、复式档案、AI 分析档案，
    使同一轮发布/复式/AI 闭环按新规则整体重出并重新冻结。
事后由维护者移除 update_dlt_d1.py 中的调用与本文件。
"""
import json
import os
from datetime import datetime, timezone

DEADLINE = datetime(2026, 10, 22, 13, 0, tzinfo=timezone.utc)
WORKFLOW_NAME = "大乐透AI娱乐分析"
DLT_TARGET = "26121"
GAME_TARGETS = {"ssq": "26121", "fc3d": "2026281", "pl3": "26281", "pl5": "26281"}


def _append_sql(out_path: str) -> None:
    lines = ["-- one-off reset F 2026-10-22 (user-ordered regeneration under AI-synthesis mechanism)"]
    lines.append(f"DELETE FROM dlt_recommendations WHERE target_issue = '{DLT_TARGET}';")
    for game, target in GAME_TARGETS.items():
        for tbl in ("recommendations", "plans", "analysis"):
            lines.append(f"DELETE FROM {game}_{tbl} WHERE target_issue = '{target}';")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[one-off reset F] appended {len(lines) - 1} DELETEs -> {out_path}")


def _drop_entries(path: str, list_key: str, field: str, value: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"[one-off reset F] skip {path}: {type(exc).__name__}")
        return
    rows = data.get(list_key)
    if not isinstance(rows, list):
        print(f"[one-off reset F] unexpected shape {path}")
        return
    kept = [x for x in rows if str(x.get(field)) != value]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data | {list_key: kept}, fh, ensure_ascii=False, indent=1)
    print(f"[one-off reset F] {path}: removed {len(rows) - len(kept)} ({field}={value})")


def run(out_path: str) -> None:
    if os.environ.get("GITHUB_WORKFLOW") != WORKFLOW_NAME:
        return
    if datetime.now(timezone.utc) >= DEADLINE:
        print("[one-off reset F] expired, skip")
        return
    _append_sql(out_path)
    _drop_entries("public/data/published_recommendations.json", "items", "issue", DLT_TARGET)
    _drop_entries("public/data/compound_archive.json", "items", "target_issue", DLT_TARGET)
    _drop_entries("public/data/ai_cycle_archive.json", "analyses", "issue", DLT_TARGET)
