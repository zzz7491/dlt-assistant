"""Pailie 5 statistics and entertainment picks (mirrors the 3D mode).

Positional game with five positions （万/千/百/十/个）: per-position
frequency and omission for digits 0-9, plus the sum distribution
(0-45). Strategies, locked with INSERT OR IGNORE:
A balanced per position, B hot/cold pattern,
C-AI智能型： LLM 基于近100期分位频率+遗漏统计摘要直接出号
（与 A/B 同口径）；无密钥或调用失败则跳过该策略，失败则跳过该策略
（用户 2026-10-20：C 改为 AI 出号）。
"""
from __future__ import annotations

import datetime

DIGITS = range(10)
POSITIONS = 5
MAX_SUM = 45


def _empty() -> list[dict[int, int]]:
    return [{d: 0 for d in DIGITS} for _ in range(POSITIONS)]


def frequency(rows: list[dict], window: int | None = None) -> dict:
    sample = rows[-window:] if window else rows
    per_position = _empty()
    for row in sample:
        for pos, digit in enumerate(row["digits"]):
            per_position[pos][digit] += 1
    return {"per_position": per_position, "sample": len(sample)}


def omission(rows: list[dict]) -> list[dict[int, int]]:
    result = [{d: len(rows) for d in DIGITS} for _ in range(POSITIONS)]
    for idx, row in enumerate(reversed(rows)):
        for pos, digit in enumerate(row["digits"]):
            if result[pos][digit] == len(rows):
                result[pos][digit] = idx
    return result


def sum_distribution(rows: list[dict], window: int | None = None) -> dict[int, int]:
    sample = rows[-window:] if window else rows
    dist = {total: 0 for total in range(MAX_SUM + 1)}
    for row in sample:
        dist[sum(row["digits"])] += 1
    return dist


def summarize(rows: list[dict]) -> dict:
    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    hot, cold = [], []
    for pos in range(POSITIONS):
        hot.append(max(DIGITS, key=lambda d: (freq_100["per_position"][pos][d], -d)))
        cold.append(max(DIGITS, key=lambda d: (omit[pos][d], -d)))
    dist = sum_distribution(rows, 100)
    common_sum = max(range(MAX_SUM + 1), key=lambda t: (dist[t], -t))
    return {
        "total_draws": len(rows),
        "frequency_100": freq_100,
        "omission": omit,
        "hot": hot,
        "cold": cold,
        "common_sum_100": common_sum,
    }


def next_target(latest: dict) -> dict:
    """Next draw (daily): next calendar day, issue +1 or year rollover."""
    day = datetime.date.fromisoformat(latest["date"]) + datetime.timedelta(days=1)
    if day.year != int(latest["date"][:4]):
        issue = f"{day.year % 100:02d}001"
    else:
        issue = f"{int(latest['issue']) + 1:05d}"
    return {"issue": issue, "date": day.isoformat()}


def generate_c_ai(target_issue: str, rows: list[dict]) -> dict | None:
    """C-AI智能型：LLM 基于与 A/B 相同的统计口径直接出号。

    统计口径：frequency(rows, 100) + omission(rows) —— 近100期分位频率
    + 全量遗漏，与 generate_picks 的 A/B 完全一致。
    无密钥或调用失败 → None（调用方跳过 C，失败则跳过该策略）。
    """
    from src.common import ai_pick  # 延迟导入，避免循环依赖

    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    positions = []
    for pos in range(POSITIONS):
        hot = max(DIGITS, key=lambda d: (freq_100["per_position"][pos][d], -d))
        cold = max(DIGITS, key=lambda d: (omit[pos][d], -d))
        top5 = sorted(
            DIGITS, key=lambda d: (-freq_100["per_position"][pos][d], d)
        )[:5]
        positions.append(
            {
                "pos": pos,
                "frequency_100_top5": {d: freq_100["per_position"][pos][d] for d in top5},
                "hot": hot,
                "cold": cold,
                "omission_top5": {
                    d: omit[pos][d]
                    for d in sorted(DIGITS, key=lambda d: (-omit[pos][d], d))[:5]
                },
            }
        )
    summary = {
        "game": "pl5",
        "positions": positions,
        "last_10": [
            {"issue": r.get("issue"), "digits": r["digits"]} for r in rows[-10:]
        ],
    }
    numbers = ai_pick.pick("pl5", target_issue, summary)
    if numbers is None:
        return None
    return {"strategy": "C-AI智能型", "digits": numbers["digits"]}


def generate_picks(target_issue: str, rows: list[dict]) -> list[dict]:
    """A/B 统计策略 + C-AI智能型（无密钥/失败时跳过 C）。"""
    if len(rows) < 100:
        raise ValueError("need at least 100 draws for statistics picks")
    freq_100 = frequency(rows, 100)
    omit = omission(rows)

    def balanced(pos: int) -> int:
        return max(
            DIGITS,
            key=lambda d: (
                freq_100["per_position"][pos][d] + min(omit[pos][d], 20) * 0.3,
                -d,
            ),
        )

    def hottest(pos: int) -> int:
        return max(DIGITS, key=lambda d: (freq_100["per_position"][pos][d], -d))

    def coldest(pos: int) -> int:
        return max(DIGITS, key=lambda d: (omit[pos][d], -d))

    picks_a = [balanced(pos) for pos in range(POSITIONS)]
    picks_b = [hottest(0), coldest(1), balanced(2), coldest(3), hottest(4)]
    picks = [
        {"strategy": "A-均衡统计型", "digits": picks_a},
        {"strategy": "B-冷热组合型", "digits": picks_b},
    ]
    pick_c = generate_c_ai(target_issue, rows)
    if pick_c is not None:
        picks.append(pick_c)
    return picks


def position_scores(rows: list[dict]) -> list[dict]:
    """Balanced score per digit for each position."""
    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    return [
        {
            d: freq_100["per_position"][pos][d] + min(omit[pos][d], 20) * 0.3
            for d in DIGITS
        }
        for pos in range(POSITIONS)
    ]


def generate_plans(target_issue: str, rows: list[dict], picks: list[dict]) -> list[dict]:
    """Single + compound plans (DLT homepage parity).

    - single: the A-strategy direct pick with per-position score basis.
    - combo: top-2 scored digits per position as a direct compound
      (2^5 = 32 bets, 64 yuan).
    """
    scores = position_scores(rows)
    freq_100 = frequency(rows, 100)
    omit = omission(rows)
    pick_a = picks[0]
    single = {
        "digits": pick_a["digits"],
        "basis": [
            {
                "position": pos,
                "digit": pick_a["digits"][pos],
                "freq100": freq_100["per_position"][pos][pick_a["digits"][pos]],
                "omission": omit[pos][pick_a["digits"][pos]],
                "score": round(scores[pos][pick_a["digits"][pos]], 1),
            }
            for pos in range(POSITIONS)
        ],
    }
    pools = [
        sorted(sorted(DIGITS, key=lambda d: (-scores[pos][d], d))[:2])
        for pos in range(POSITIONS)
    ]
    bets = 1
    for pool in pools:
        bets *= len(pool)
    combo = {"pools": pools, "bets": bets, "cost_yuan": bets * 2}
    return [
        {"kind": "single", "payload": single},
        {"kind": "combo", "payload": combo},
    ]
