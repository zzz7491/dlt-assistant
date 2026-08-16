"""娱乐推荐记录落盘：供开奖验证模块(T2)比对使用。

每条记录字段：
  date        生成日期（YYYY-MM-DD）
  target_issue 这组推荐预测的「下一期」期号（5 位 YYNNN）
  strategy    推荐策略名称（T3 起为 A/B/C，当前为单策略占位）
  front / back 推荐的前区5码 / 后区2码

注意：仅为娱乐记录，不预测中奖。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any


def next_issue(latest: int) -> int:
    """给定最新 5 位期号，返回下一期期号（处理跨年：年末 → 次年 001）。"""
    nn = latest % 1000
    yy = latest // 1000
    if nn >= 353:  # 大乐透每年约 ≤153 期，353 为安全上界
        return (yy + 1) * 1000 + 1
    return latest + 1


def _key(rec: dict[str, Any]) -> tuple:
    # 去重键：目标期号 + 策略 + 组内序号（不含具体号码），使同一目标期同一策略只保留最新一组
    return (rec["target_issue"], rec["strategy"], rec.get("idx", 0))


def load(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path: str, new_recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并推荐记录：按 (目标期号, 策略, 序号) 去重，同一键仅保留最新一组（覆盖式）。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    existing = load(path)
    merged = {_key(r): r for r in existing}        # 已有记录按键索引
    for r in new_recs:
        merged[_key(r)] = r                        # 新记录覆盖同键旧记录
    result = sorted(merged.values(), key=lambda r: (r["target_issue"], r.get("date", "")))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def build_records(combos: list[dict[str, Any]], target_issue: int, strategy: str,
                  date: str | None = None) -> list[dict[str, Any]]:
    date = date or datetime.now().strftime("%Y-%m-%d")
    return [
        {"date": date, "target_issue": str(target_issue), "strategy": strategy,
         "idx": i, "front": c["front"], "back": c["back"]}
        for i, c in enumerate(combos)
    ]
