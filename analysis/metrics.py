"""指标计算模块（metrics）——与 score.js 同口径（逐函数迁移）。

Task 1.1-B：六项指标 + frequency 全部实现，与前端 score.js 同输入同输出
（取整统一用 js_round，对齐 JS Math.round 行为，避免银行家舍入差异）。

指标清单：
  slice_window          窗口提取（n=数字或 "all"）
  calculate_frequency   频率（全池计数）
  calculate_hot         热度 [{num, count, omit}]（count 倒序）
  calculate_missing     遗漏 [{num, cur, max, avg}]
  calculate_odd_even    奇偶占比 {odd, even, total}
  calculate_big_small   大小占比 {small, big, total}
  calculate_consec      连号参与期数 {num: 期数}
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Union

FRONT_MIN, FRONT_MAX = 1, 35
BACK_MIN, BACK_MAX = 1, 12
FRONT_BOUNDARY = 17   # 前区：01-17 小 / 18-35 大（与 score.js 一致）
BACK_BOUNDARY = 6     # 后区：01-06 小 / 07-12 大

Window = Union[int, str]  # 数字窗口或 "all"


def js_round(x: float) -> int:
    """JS Math.round 等价（正数）：Math.round(x) = floor(x + 0.5)。"""
    return int(math.floor(x + 0.5))


def clamp(v: float, lo: int, hi: int) -> int:
    """与 score.js clamp 一致：min(hi, max(lo, v)) 后取整。"""
    return min(hi, max(lo, int(v)))


def _range(a: int, b: int) -> List[int]:
    return list(range(a, b + 1))


def _pool(kind: str) -> List[int]:
    return _range(FRONT_MIN, FRONT_MAX) if kind == "front" else _range(BACK_MIN, BACK_MAX)


def slice_window(issues: List[Dict[str, Any]], n: Window) -> List[Dict[str, Any]]:
    """取最近 n 期；n="all" 返回全部（与 score.js sliceWindow 同规格）。"""
    if n == "all":
        return list(issues)
    return list(issues[max(0, len(issues) - int(n)):])


def calculate_frequency(issues: List[Dict[str, Any]], n: Window, kind: str) -> List[Dict[str, Any]]:
    """全池出现次数：[{num, count}]（前区 35 / 后区 12 全码计数）。"""
    w = slice_window(issues, n)
    freq = {x: 0 for x in _pool(kind)}
    for it in w:
        for x in it[kind]:
            freq[x] = freq.get(x, 0) + 1
    return [{"num": x, "count": freq[x]} for x in _pool(kind)]


def calculate_hot(issues: List[Dict[str, Any]], n: Window, kind: str) -> List[Dict[str, Any]]:
    """热度：[{num, count, omit}]，count 倒序；omit=距最新一期连续未出现期数。"""
    w = slice_window(issues, n)
    freq: Dict[int, int] = {}
    last: Dict[int, int] = {}
    for idx, it in enumerate(w):
        for x in it[kind]:
            freq[x] = freq.get(x, 0) + 1
            last[x] = idx
    last_idx = len(w) - 1
    out = [{
        "num": x,
        "count": freq.get(x, 0),
        "omit": last_idx - last.get(x, last_idx),
    } for x in _pool(kind)]
    out.sort(key=lambda h: h["count"], reverse=True)
    return out


def calculate_missing(issues: List[Dict[str, Any]], n: Window, kind: str) -> List[Dict[str, Any]]:
    """遗漏：[{num, cur, max, avg}]（当前/最大/平均连续未出现段）。"""
    w = slice_window(issues, n)
    out = []
    for num in _pool(kind):
        # 当前遗漏
        cur = 0
        for i in range(len(w) - 1, -1, -1):
            if num in w[i][kind]:
                break
            cur += 1
        # 遗漏段统计
        run, max_run, total_run, run_count = 0, 0, 0, 0
        for j in range(len(w)):
            if num in w[j][kind]:
                if run > 0:
                    total_run += run
                    run_count += 1
                    max_run = max(max_run, run)
                    run = 0
            else:
                run += 1
        if run > 0:
            total_run += run
            run_count += 1
            max_run = max(max_run, run)
        # round1 对齐 JS：Math.round(v*10)/10（避免银行家舍入差异）
        avg = (js_round(total_run / run_count * 10) / 10) if run_count else 0
        out.append({"num": num, "cur": cur, "max": max_run, "avg": avg})
    return out


def calculate_odd_even(issues: List[Dict[str, Any]], n: Window, kind: str) -> Dict[str, Any]:
    """奇偶占比：{odd, even, total}（百分比，round1）。"""
    w = slice_window(issues, n)
    odd = even = 0
    for it in w:
        for x in it[kind]:
            if x % 2 == 1:
                odd += 1
            else:
                even += 1
    t = odd + even
    return {
        "odd": (js_round(odd / t * 100 * 10) / 10) if t else 50,
        "even": (js_round(even / t * 100 * 10) / 10) if t else 50,
        "total": t,
    }


def calculate_big_small(issues: List[Dict[str, Any]], n: Window, kind: str,
                        boundary: int = FRONT_BOUNDARY) -> Dict[str, Any]:
    """大小占比：{small, big, total}。boundary 前区 17 / 后区 6（与 score.js 一致）。"""
    w = slice_window(issues, n)
    small = big = 0
    for it in w:
        for x in it[kind]:
            if x <= boundary:
                small += 1
            else:
                big += 1
    t = small + big
    return {
        "small": (js_round(small / t * 100 * 10) / 10) if t else 50,
        "big": (js_round(big / t * 100 * 10) / 10) if t else 50,
        "total": t,
    }


def calculate_consec(issues: List[Dict[str, Any]], n: Window, kind: str) -> Dict[int, int]:
    """连号参与期数：{num: 该号码参与连号（相邻差=1）的期数}（与 score.js calculateConsec 同口径）。"""
    w = slice_window(issues, n)
    counts: Dict[int, int] = {}
    for it in w:
        s = sorted(it[kind])
        for i, x in enumerate(s):
            if (i > 0 and s[i - 1] == x - 1) or (i < len(s) - 1 and s[i + 1] == x + 1):
                counts[x] = counts.get(x, 0) + 1
    return counts
