"""P2-1 大乐透奖级分类器与成本/回报（按官方规则，不猜奖金）。

官方大乐透奖级（前区命中 fh / 后区命中 bh）：

  一等  5+2   浮动奖金（不编造金额）
  二等  5+1   浮动奖金（不编造金额）
  三等  5+0   固定 10000
  四等  4+2   固定 3000
  五等  4+1   固定 300
  六等  3+2   固定 200
  七等  4+0   固定 100
  八等  3+1 / 2+2   固定 15
  九等  3+0 / 2+1 / 1+2 / 0+2   固定 5
  未中  其余

单注标准投注成本 = 2 RMB。

设计原则（P2-1 任务书 STEP 8）：
  - 固定奖金等级按官方规则计算；
  - 浮动奖金（一/二等）**不编造具体金额** → 输出 variable_prize_count；
  - ROI 只能给 lower_bound（仅计入已知固定奖），浮动部分标记
    roi_not_fully_determinable。
"""
from __future__ import annotations

from typing import Any

# 单注成本（标准 2 元）
TICKET_COST = 2.0

# 固定奖金金额（官方规则；一等/二等为浮动，不含此表）
FIXED_PRIZE: dict[int, float] = {
    3: 10000.0,
    4: 3000.0,
    5: 300.0,
    6: 200.0,
    7: 100.0,
    8: 15.0,
    9: 5.0,
}

VARIABLE_TIERS = (1, 2)


def classify_prize(front_hits: int, back_hits: int) -> int | None:
    """返回奖级（1-9）或 None（未中奖）。

    入参为命中数量，与顺序无关。
    """
    fh, bh = int(front_hits), int(back_hits)
    if fh < 0 or bh < 0:
        raise ValueError("hit counts must be >= 0")
    key = (fh, bh)
    if key == (5, 2):
        return 1
    if key == (5, 1):
        return 2
    if key == (5, 0):
        return 3
    if key == (4, 2):
        return 4
    if key == (4, 1):
        return 5
    if key == (3, 2):
        return 6
    if key == (4, 0):
        return 7
    if key in ((3, 1), (2, 2)):
        return 8
    if key in ((3, 0), (2, 1), (1, 2), (0, 2)):
        return 9
    return None


def payout_breakdown(front_hits: int, back_hits: int) -> dict[str, Any]:
    """单注回报分解：

      known_fixed_payout     固定等级奖金合计（一/二等不计）
      variable_prize_count   命中的浮动奖级数（1/2 等）
      is_variable_hit        是否命中浮动奖（一/二等）
      roi_lower_bound        仅按固定奖计算的 ROI 下界（相对 2 元成本）
      roi_fully_determinable 是否可精确判定 ROI（命中浮动奖 → False）
    """
    tier = classify_prize(front_hits, back_hits)
    if tier is None:
        return {
            "tier": None,
            "known_fixed_payout": 0.0,
            "variable_prize_count": 0,
            "is_variable_hit": False,
            "roi_lower_bound": -TICKET_COST / TICKET_COST,  # 全损 = -1.0
            "roi_fully_determinable": True,
        }
    fixed = FIXED_PRIZE.get(tier, 0.0)
    variable = tier in VARIABLE_TIERS
    var_count = 1 if variable else 0
    known = fixed
    # 命中浮动奖：精确金额未知 → ROI 不可完全判定（下界=固定部分）
    roi_lb = (known - TICKET_COST) / TICKET_COST
    return {
        "tier": tier,
        "known_fixed_payout": known,
        "variable_prize_count": var_count,
        "is_variable_hit": variable,
        "roi_lower_bound": round(roi_lb, 4),
        "roi_fully_determinable": not variable,
    }


def aggregate_payout(records: list[dict[str, Any]]) -> dict[str, Any]:
    """对一批评测记录汇总成本/回报。

    records: 每条含 front_hits / back_hits（或已含 payout 分解）。
    输出：
      n, cost_total, known_fixed_payout_total, variable_prize_count,
      prize_tier_counts, roi_lower_bound_total, roi_fully_determinable
    """
    cost = 0.0
    fixed = 0.0
    var = 0
    tiers: dict[str, int] = {}
    all_fixed = True
    for r in records:
        fh, bh = int(r["front_hits"]), int(r["back_hits"])
        pb = payout_breakdown(fh, bh)
        cost += TICKET_COST
        fixed += pb["known_fixed_payout"]
        var += pb["variable_prize_count"]
        all_fixed = all_fixed and pb["roi_fully_determinable"]
        key = str(pb["tier"])
        tiers[key] = tiers.get(key, 0) + 1
    return {
        "n": len(records),
        "cost_total": round(cost, 2),
        "known_fixed_payout_total": round(fixed, 2),
        "variable_prize_count": var,
        "prize_tier_counts": tiers,
        "roi_lower_bound_total": round((fixed - cost) / cost, 4) if cost else 0.0,
        "roi_fully_determinable": all_fixed,
    }
