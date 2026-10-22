"""Shuangseqiu statistics and entertainment picks (mirrors DLT mode).

Statistics are computed from the stored draw history: all-time and
last-100 frequency, current omission (draws since last appearance),
and hot/cold tags. Picks follow the DLT three-strategy pattern and
are deterministic per target issue, then locked in D1 with
INSERT OR IGNORE (first write wins, exactly like dlt_recommendations):

- A-均衡统计型： balanced scores (last-100 frequency + moderate omission)
  spread across the three red zones.
- B-冷热组合型： hot numbers mixed with high-omission cold numbers.
- C-AI智能型： LLM 直接出号，统计摘要与 A/B 同口径
  （frequency(rows, 100) + omission(rows)）；无密钥或调用失败则跳过
  该策略，失败则跳过该策略（用户 2026-10-20：C 改为 AI 出号）。
"""
from __future__ import annotations

import datetime

RED_RANGE = range(1, 34)
BLUE_RANGE = range(1, 17)
DRAW_WEEKDAYS = {1, 3, 6}  # Tue / Thu / Sun


def frequency(rows: list[dict], window: int | None = None) -> dict:
    """Ball frequency over the latest ``window`` draws (None = all)."""
    sample = rows[-window:] if window else rows
    red = {n: 0 for n in RED_RANGE}
    blue = {n: 0 for n in BLUE_RANGE}
    for row in sample:
        for n in row["red"]:
            red[n] += 1
        blue[row["blue"]] += 1
    return {"red": red, "blue": blue, "sample": len(sample)}


def omission(rows: list[dict]) -> dict:
    """Draws since each ball last appeared (len(rows) if never)."""
    red = {n: len(rows) for n in RED_RANGE}
    blue = {n: len(rows) for n in BLUE_RANGE}
    for idx, row in enumerate(reversed(rows)):
        for n in row["red"]:
            if red[n] == len(rows):
                red[n] = idx
        if blue[row["blue"]] == len(rows):
            blue[row["blue"]] = idx
    return {"red": red, "blue": blue}


def summarize(rows: list[dict]) -> dict:
    """Compact statistics bundle used by the API and the page."""
    freq_all = frequency(rows)
    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    hot_red = sorted(RED_RANGE, key=lambda n: (-freq_100["red"][n], n))[:6]
    cold_red = sorted(RED_RANGE, key=lambda n: (-omit["red"][n], n))[:6]
    hot_blue = sorted(BLUE_RANGE, key=lambda n: (-freq_100["blue"][n], n))[:3]
    cold_blue = sorted(BLUE_RANGE, key=lambda n: (-omit["blue"][n], n))[:3]
    return {
        "total_draws": len(rows),
        "frequency_all": freq_all,
        "frequency_100": freq_100,
        "omission": omit,
        "hot": {"red": hot_red, "blue": hot_blue},
        "cold": {"red": cold_red, "blue": cold_blue},
    }


def next_target(latest: dict) -> dict:
    """Next draw's issue and date after ``latest`` (Tue/Thu/Sun)."""
    day = datetime.date.fromisoformat(latest["date"]) + datetime.timedelta(days=1)
    while day.weekday() not in DRAW_WEEKDAYS:
        day += datetime.timedelta(days=1)
    if day.year != int(latest["date"][:4]):
        issue = f"{day.year % 100:02d}001"
    else:
        issue = f"{int(latest['issue']) + 1:05d}"
    return {"issue": issue, "date": day.isoformat()}


def _zone(number: int) -> int:
    return 0 if number <= 11 else (1 if number <= 22 else 2)


def generate_c_ai(target_issue: str, rows: list[dict]) -> dict | None:
    """C-AI智能型：LLM 基于与 A/B 相同的统计口径直接出号。

    统计口径（与 generate_picks 的 A/B 完全一致）：
    frequency(rows, 100) + omission(rows) —— 近100期频率 + 全量遗漏。
    无密钥或调用失败 → None（调用方跳过 C，失败则跳过该策略）。
    """
    from src.common import ai_pick  # 延迟导入，避免循环依赖

    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    hot_red = sorted(RED_RANGE, key=lambda n: (-freq_100["red"][n], n))[:6]
    cold_red = sorted(RED_RANGE, key=lambda n: (-omit["red"][n], n))[:6]
    hot_blue = sorted(BLUE_RANGE, key=lambda n: (-freq_100["blue"][n], n))[:3]
    cold_blue = sorted(BLUE_RANGE, key=lambda n: (-omit["blue"][n], n))[:3]
    summary = {
        "game": "ssq",
        "frequency_100_top_red": {n: freq_100["red"][n] for n in hot_red},
        "frequency_100_top_blue": {n: freq_100["blue"][n] for n in hot_blue},
        "hot_red": hot_red,
        "cold_red": cold_red,
        "hot_blue": hot_blue,
        "cold_blue": cold_blue,
        "omission_top_red": {n: omit["red"][n] for n in cold_red},
        "omission_top_blue": {n: omit["blue"][n] for n in cold_blue},
        "last_10": [
            {
                "issue": r.get("issue"),
                "red": r["red"],
                "blue": r["blue"],
            }
            for r in rows[-10:]
        ],
    }
    numbers = ai_pick.pick("ssq", target_issue, summary)
    if numbers is None:
        return None
    return {"strategy": "C-AI智能型", "red": numbers["red"], "blue": numbers["blue"]}


def generate_trend_ai(target_issue: str, rows: list[dict]) -> dict | None:
    """D-走势AI型：AI 看最近300期走势图数据直接研判出号（2026-10-22 用户指令）。

    输入为 src/common/trend_data.ball_trend 的走势图文本形态（逐期开奖、
    和值/跨度曲线、各号出号条），不用频率/遗漏统计口径。
    无密钥或调用失败 → None（调用方跳过该策略，失败则跳过）。
    """
    from src.common import ai_pick, trend_data  # 延迟导入，避免循环依赖

    trend = trend_data.ball_trend(
        [(r["red"], r["blue"]) for r in rows], RED_RANGE, BLUE_RANGE
    )
    numbers = ai_pick.pick_trend("ssq", target_issue, trend)
    if numbers is None:
        return None
    return {"strategy": "D-走势AI型", "red": numbers["red"], "blue": numbers["blue"]}


def generate_picks(target_issue: str, rows: list[dict]) -> list[dict]:
    """A/B 统计策略 + C-AI智能型（无密钥/失败时跳过 C）。"""
    if len(rows) < 100:
        raise ValueError("need at least 100 draws for statistics picks")
    freq_100 = frequency(rows, 100)
    omit = omission(rows)

    # A-均衡统计型： score = freq100 + omission bonus, two per zone.
    scored = {
        n: freq_100["red"][n] + min(omit["red"][n], 20) * 0.3 for n in RED_RANGE
    }
    reds_a: list[int] = []
    for zone in range(3):
        in_zone = [n for n in RED_RANGE if _zone(n) == zone]
        in_zone.sort(key=lambda n: (-scored[n], n))
        reds_a.extend(in_zone[:2])
    blue_a = max(BLUE_RANGE, key=lambda n: (freq_100["blue"][n], -n))

    # B-冷热组合型： 3 hot + 2 cold + 1 best-omission blue pairing.
    hot = sorted(RED_RANGE, key=lambda n: (-freq_100["red"][n], n))[:3]
    cold = [
        n
        for n in sorted(RED_RANGE, key=lambda n: (-omit["red"][n], n))
        if n not in hot
    ][:2]
    mid = [
        n
        for n in sorted(RED_RANGE, key=lambda n: (-scored[n], n))
        if n not in hot and n not in cold
    ][:1]
    reds_b = hot + cold + mid
    blue_b = max(
        (n for n in BLUE_RANGE if n != blue_a),
        key=lambda n: (omit["blue"][n], -n),
    )

    picks = [
        {"strategy": "A-均衡统计型", "red": sorted(reds_a), "blue": blue_a},
        {"strategy": "B-冷热组合型", "red": sorted(reds_b), "blue": blue_b},
    ]
    pick_c = generate_c_ai(target_issue, rows)
    if pick_c is not None:
        picks.append(pick_c)
    pick_t = generate_trend_ai(target_issue, rows)
    if pick_t is not None:
        picks.append(pick_t)
    return picks


def number_scores(rows: list[dict]) -> tuple[dict, dict]:
    """Balanced scores per ball (freq100 + omission bonus)."""
    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    red = {
        n: freq_100["red"][n] + min(omit["red"][n], 20) * 0.3 for n in RED_RANGE
    }
    blue = {
        n: freq_100["blue"][n] + min(omit["blue"][n], 12) * 0.3 for n in BLUE_RANGE
    }
    return red, blue


def generate_plans(target_issue: str, rows: list[dict], picks: list[dict]) -> list[dict]:
    """Single + compound plans for ``target_issue`` (DLT homepage parity).

    - single （本期唯一推荐）: the A-strategy pick, with its score basis.
    - combo （本期组合推荐）: top-8 red pool + top-2 blue pool compound
      (C(8,6)*2 = 56 bets, 112 yuan), pools ranked by balanced score.
    """
    import math

    red_scores, blue_scores = number_scores(rows)
    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    pick_a = picks[0]
    single = {
        "red": pick_a["red"],
        "blue": pick_a["blue"],
        "basis": [
            {
                "number": n,
                "freq100": freq_100["red"][n],
                "omission": omit["red"][n],
                "score": round(red_scores[n], 1),
            }
            for n in pick_a["red"]
        ],
        "blue_basis": {
            "number": pick_a["blue"],
            "freq100": freq_100["blue"][pick_a["blue"]],
            "omission": omit["blue"][pick_a["blue"]],
        },
    }
    ranked_red = sorted(RED_RANGE, key=lambda n: (-red_scores[n], n))
    ranked_blue = sorted(BLUE_RANGE, key=lambda n: (-blue_scores[n], n))
    pool_red = sorted(ranked_red[:8])
    pool_blue = sorted(ranked_blue[:2])
    bets = math.comb(len(pool_red), 6) * len(pool_blue)
    combo = {
        "red_pool": pool_red,
        "blue_pool": pool_blue,
        "bets": bets,
        "cost_yuan": bets * 2,
    }
    return [
        {"kind": "single", "payload": single},
        {"kind": "combo", "payload": combo},
    ]
