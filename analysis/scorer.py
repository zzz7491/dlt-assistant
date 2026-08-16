"""三模型评分模块（scorer）——与 score.js 同规格（scoreAll 逐函数迁移）。

Task 1.1-B：score_all 完整实现。SCORE_MODELS 与 score.js 逐值一致；
js_round 对齐 JS Math.round（避免银行家舍入差异）。

输出 [{num, total, parts{7 维贡献分}, tag}]：
  - total 0-100
  - parts 七项之和 = total（可核对）
  - 按 total 降序（稳定排序，同分保持号码升序，与 JS 稳定 sort 一致）
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from analysis.metrics import (FRONT_BOUNDARY, BACK_BOUNDARY, _pool, js_round, clamp,
                              slice_window, calculate_hot, calculate_missing,
                              calculate_odd_even, calculate_big_small, calculate_consec)

# 权重表（与 score.js SCORE_MODELS 逐值一致，禁止改动；各模型和 = 1.0）
SCORE_MODELS: Dict[str, Dict[str, float]] = {
    "standard": {
        "frequency": 0.25,
        "recentHot": 0.20,
        "missing": 0.15,
        "balance": 0.15,
        "oddEven": 0.10,
        "bigSmall": 0.10,
        "structure": 0.05,
    },
    "cold-hot": {
        "frequency": 0.20,
        "recentHot": 0.25,
        "missing": 0.15,
        "balance": 0.20,
        "oddEven": 0.10,
        "bigSmall": 0.05,
        "structure": 0.05,
    },
    "expert": {
        "frequency": 0.20,
        "recentHot": 0.20,
        "missing": 0.15,
        "balance": 0.10,
        "oddEven": 0.10,
        "bigSmall": 0.10,
        "structure": 0.15,
    },
}

MODEL_TYPES: List[str] = ["standard", "cold-hot", "expert"]

PART_KEYS: List[str] = ["frequency", "recentHot", "missing", "balance",
                        "oddEven", "bigSmall", "structure"]

SCORE_VERSION = {
    "scoreVersion": "v1.1",
    "weightVersion": "default",
    "generatedFrom": "1000期历史开奖数据",
    "modelTypes": MODEL_TYPES,
}


def miss_score(cur: float, avg: float) -> int:
    """遗漏周期分：倒 U 形回摆（与 score.js missScore 一致）。"""
    if avg <= 0:
        return 50
    if cur <= avg:
        return clamp(js_round(cur / avg * 80), 0, 100)
    if cur <= 2 * avg:
        return clamp(js_round(80 + (cur - avg) / avg * 20), 0, 100)
    return clamp(js_round(100 - (cur - 2 * avg) / avg * 30), 0, 100)


def _tag_for(rank_idx: int, length: int) -> str:
    """冷热标签：🔥热号 / ⚖平衡 / ❄冷号（频率排名三分位，与 score.js 同口径）。"""
    if length <= 1:
        return "⚖平衡"
    r = rank_idx / (length - 1)
    if r < 1 / 3:
        return "🔥热号"
    if r > 2 / 3:
        return "❄冷号"
    return "⚖平衡"


def _score_number(num: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """单号码评分（与 score.js scoreNumber 同规格）。"""
    w = ctx["window"]
    n_len = len(w)
    hm = ctx["hot_map"].get(num)
    count = hm["count"] if hm else 0
    omit = ctx["miss_map"][num]["cur"] if num in ctx["miss_map"] else 0
    avg = ctx["miss_map"][num]["avg"] if num in ctx["miss_map"] else 0
    avg_count = n_len * 5 / (35 if ctx["kind"] == "front" else 12)
    max_count = ctx["max_count"]
    odd_pct = ctx["odd_pct"] if num % 2 == 1 else ctx["even_pct"]
    small_pct = ctx["small_pct"] if num <= ctx["boundary"] else ctx["big_pct"]
    consec_count = ctx["consec_map"].get(num, 0)

    s_frequency = clamp(js_round(count / avg_count * 50), 0, 100)
    s_recent_hot = clamp(js_round(count / max_count * 100 if max_count else 50), 0, 100)
    s_missing = miss_score(omit, avg)
    s_balance = ctx["balance_map"][num]
    s_odd_even = clamp(js_round(odd_pct), 0, 100)
    s_big_small = clamp(js_round(small_pct), 0, 100)
    s_structure = clamp(js_round(consec_count / n_len * 150 if n_len else 50), 0, 100)

    weights = ctx["weights"]
    parts = {
        "frequency": js_round(weights["frequency"] * s_frequency),
        "recentHot": js_round(weights["recentHot"] * s_recent_hot),
        "missing": js_round(weights["missing"] * s_missing),
        "balance": js_round(weights["balance"] * s_balance),
        "oddEven": js_round(weights["oddEven"] * s_odd_even),
        "bigSmall": js_round(weights["bigSmall"] * s_big_small),
        "structure": js_round(weights["structure"] * s_structure),
    }
    total = sum(parts.values())
    return {"num": num, "total": total, "parts": parts, "tag": ctx["tag_map"][num]}


def score_all(issues: List[Dict[str, Any]], period: Any, kind: str,
              model_type: str = "standard") -> List[Dict[str, Any]]:
    """批量评分：kind = 'front' | 'back'；period = 数字窗口或 'all'。

    与 score.js scoreAll 同规格：返回按 total 降序的
    [{num, total, tag, parts{7 维贡献分}}]，七项之和 = total（0-100）。
    """
    if model_type not in SCORE_MODELS:
        raise ValueError(f"未知模型: {model_type}（可选 {MODEL_TYPES}）")
    n = len(issues) if period == "all" else int(period)
    w = slice_window(issues, n)
    n_len = len(w)
    pool = _pool(kind)
    boundary = FRONT_BOUNDARY if kind == "front" else BACK_BOUNDARY

    hot = calculate_hot(issues, n, kind)
    miss = calculate_missing(issues, n, kind)
    miss_map = {m["num"]: m for m in miss}
    hot_map = {h["num"]: h for h in hot}
    hot_order = [h["num"] for h in hot]
    oe = calculate_odd_even(issues, n, kind)
    bs = calculate_big_small(issues, n, kind, boundary)
    consec_map = calculate_consec(issues, n, kind)
    max_count = hot[0]["count"] if hot else 0

    # 冷热平衡分：按窗口频率排名三分位基分 + 近期热度微调（过热衰减/过冷补偿）
    # 与 JS 完全一致：hotAdj = clamp(Math.round(pct-50)/100*16, -8, 8)【先 round 再乘，clamp 不取整】
    #             balance = clamp(Math.round(base + hotAdj), 20, 95)
    rank_map: Dict[int, float] = {}
    for idx, num in enumerate(hot_order):
        rank_map[num] = idx / max(1, len(hot_order) - 1)
    balance_map: Dict[int, int] = {}
    for num in pool:
        r = rank_map.get(num)
        base = 72 if r is not None and r < 1 / 3 else (42 if r is not None and r > 2 / 3 else (60 if r is not None else 50))
        hc = hot_map[num]["count"] if num in hot_map else 0
        pct = hc / max_count * 100 if max_count else 50
        hot_adj = js_round(pct - 50) / 100 * 16        # 先 round(pct-50)，再 /100*16（浮点）
        hot_adj = min(8.0, max(-8.0, hot_adj))         # clamp 不取整（与 JS Math.min/max 一致）
        balance_map[num] = clamp(js_round(base + hot_adj), 20, 95)

    # 冷热标签
    tag_map: Dict[int, str] = {}
    for num in pool:
        r = rank_map.get(num)
        if r is None:
            tag_map[num] = "⚖平衡"
        elif r < 1 / 3:
            tag_map[num] = "🔥热号"
        elif r > 2 / 3:
            tag_map[num] = "❄冷号"
        else:
            tag_map[num] = "⚖平衡"

    ctx: Dict[str, Any] = {
        "window": w, "kind": kind, "boundary": boundary,
        "weights": SCORE_MODELS[model_type],
        "hot_map": hot_map, "miss_map": miss_map, "consec_map": consec_map,
        "max_count": max_count,
        "odd_pct": oe["odd"], "even_pct": oe["even"],
        "small_pct": bs["small"], "big_pct": bs["big"],
        "balance_map": balance_map, "tag_map": tag_map,
    }
    out = [_score_number(num, ctx) for num in pool]
    out.sort(key=lambda x: x["total"], reverse=True)
    return out
