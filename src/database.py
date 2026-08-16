"""JSON 数据库读写：保存大乐透历史开奖数据（去重合并、按时区时间戳记录）。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def load(path: str) -> dict[str, Any]:
    """读取 JSON 数据库；文件不存在时返回空结构。"""
    if not os.path.exists(path):
        return {"updated_at": None, "source": None, "count": 0, "issues": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path: str, issues: list[dict[str, Any]], source: str, max_issues: int | None = None) -> dict[str, Any]:
    """按 期号 去重合并后写入 JSON 数据库，返回完整结构。

    max_issues: 若设置，合并后仅保留最近 max_issues 期（数据库封顶）。
    """
    db = load(path)
    existing = {it["issue"]: it for it in db.get("issues", [])}
    for it in issues:
        existing[it["issue"]] = it
    merged = sorted(existing.values(), key=lambda x: x["issue"])
    # 封顶：仅保留最近 max_issues 期（默认不封顶）
    if max_issues and len(merged) > max_issues:
        merged = merged[-max_issues:]
    db = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "count": len(merged),
        "issues": merged,
    }
    ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    return db
