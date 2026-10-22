"""走势图数据构造（供「走势AI型」策略，2026-10-22 用户指令）。

用户口径：彩民在彩票站主要看走势图——最近出了什么、和值/跨度曲线
往哪走、每个号码的出号形态——据此研判下一期。本模块只把最近 30 期
开奖整理成走势图的文本形态，不做频率/遗漏等统计结论，研判交给 AI：

- 逐期开奖序列（走势图的行）
- 和值、跨度逐期序列（走势图的曲线）
- 出号条：每个号码（或每个数位上的每个数字）在最近 30 期逐期的
  出/未出标记（走势图的矩阵），按时间从旧到新，末尾为最新一期。

仅用标准库；输入为调用方已按时间旧→新排序的开奖序列。
"""
from __future__ import annotations

WINDOW = 30


def _strip(draw_sets: list[set], value: int) -> str:
    """出号条：逐期 1=开出 0=未开出，左旧右新。"""
    return "".join("1" if value in s else "0" for s in draw_sets)


def ball_trend(draws: list, main_range, sub_range=None) -> dict:
    """球类走势（大乐透/双色球）。

    draws: [(主区号码 list, 副区号码 list 或单值或 None), ...]，旧→新。
    """
    rows = draws[-WINDOW:]
    main_sets = [set(m) for m, _ in rows]
    sums = [sum(m) for m, _ in rows]
    spans = [(max(m) - min(m)) if m else 0 for m, _ in rows]
    trend = {
        "window": len(rows),
        "draws": [
            {"main": sorted(m), **({"sub": sorted(s) if isinstance(s, (list, tuple, set)) else s} if s is not None else {})}
            for m, s in rows
        ],
        "sum_series": sums,
        "span_series": spans,
        "main_strips": {str(n): _strip(main_sets, n) for n in main_range},
    }
    if sub_range is not None:
        sub_sets = [
            set(s) if isinstance(s, (list, tuple, set)) else ({s} if s is not None else set())
            for _, s in rows
        ]
        trend["sub_strips"] = {str(n): _strip(sub_sets, n) for n in sub_range}
    return trend


def digit_trend(draws: list, positions: int) -> dict:
    """数字型走势（福彩3D/排列三/排列五）。

    draws: [每期各位数字 list, ...]，旧→新。
    """
    rows = draws[-WINDOW:]
    sums = [sum(d) for d in rows]
    spans = [(max(d) - min(d)) if d else 0 for d in rows]
    trend = {
        "window": len(rows),
        "draws": [list(d) for d in rows],
        "sum_series": sums,
        "span_series": spans,
        "distinct_series": [len(set(d)) for d in rows],
        "position_strips": [
            {str(d): "".join("1" if row[pos] == d else "0" for row in rows) for d in range(10)}
            for pos in range(positions)
        ],
    }
    return trend
