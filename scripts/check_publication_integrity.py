"""发布完整性校验（2026-11-01 治本）：把「静默坏掉」变成「运行标红」。

背景：26125 期 publisher 与冻结快照冲突后 fail-closed，工作流仍全绿，
展开版推荐被 plain 导出覆盖，前端与 ai_cycle 失去唯一 primary，直到
用户看主页才发现。此脚本在提交/部署之后运行，只做只读校验：

  1. recommendations.json 当前在售期恰好 1 个 is_primary；
  2. 该期在 published_recommendations.json 中有冻结快照；
  3. ai_cycle.json 的 analysis 状态不是契约类失败
     （invalid_context / frozen_identity_conflict）。

任一不满足 → exit 1（工作流标红报警）；数据已提交部署，标红不回滚。
模型不可用等非契约状态不在此列，避免瞬时故障误报。
本地用法：python scripts/check_publication_integrity.py [--dir public/data]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

CONTRACT_FAILURES = {"invalid_context", "frozen_identity_conflict"}


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def check(data_dir: str) -> list[str]:
    problems: list[str] = []
    recs = _load(os.path.join(data_dir, "recommendations.json"))
    if not isinstance(recs, list) or not recs:
        return ["recommendations.json 缺失或为空"]
    targets = {str(r.get("target_issue")) for r in recs if isinstance(r, dict)}
    if len(targets) != 1:
        problems.append(f"target_issue 不一致：{sorted(targets)}")
        return problems
    issue = next(iter(targets))
    primaries = [r for r in recs if isinstance(r, dict) and r.get("is_primary") is True]
    if len(primaries) != 1:
        problems.append(
            f"{issue} 期 is_primary 数量={len(primaries)}（契约要求恰好 1 个）")
    snaps = _load(os.path.join(data_dir, "published_recommendations.json"))
    items = snaps.get("items") if isinstance(snaps, dict) else None
    if not isinstance(items, list) or not any(
            str(s.get("issue")) == issue for s in items if isinstance(s, dict)):
        problems.append(f"{issue} 期无冻结快照")
    cyc = _load(os.path.join(data_dir, "ai_cycle.json"))
    if isinstance(cyc, dict):
        status = (cyc.get("statuses") or {}).get("analysis")
        if status in CONTRACT_FAILURES:
            problems.append(f"ai_cycle analysis 状态={status}（契约类失败）")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="发布完整性校验（只读）")
    ap.add_argument("--dir", default="public/data")
    args = ap.parse_args()
    problems = check(args.dir)
    if problems:
        for p in problems:
            print(f"🛑 发布完整性校验失败：{p}")
        return 1
    print("✅ 发布完整性校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
