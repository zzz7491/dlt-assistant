"""历史数据分析：频率、热冷号、遗漏、奇偶、大小、连号、区间分布。"""
from __future__ import annotations

from collections import Counter
from typing import Any


def analyze(issues: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    a = cfg["analysis"]
    fmin, fmax = a["front_min"], a["front_max"]
    bmin, bmax = a["back_min"], a["back_max"]

    issues = sorted(issues, key=lambda x: x["issue"])
    n = len(issues)
    window = min(a.get("recent_window", 50), n)

    # 总体频率
    front_counter: Counter = Counter()
    back_counter: Counter = Counter()
    for it in issues:
        front_counter.update(it["front"])
        back_counter.update(it["back"])
    front_freq = {i: front_counter.get(i, 0) for i in range(fmin, fmax + 1)}
    back_freq = {i: back_counter.get(i, 0) for i in range(bmin, bmax + 1)}

    # 近期窗口频率
    recent = issues[-window:]
    rfront: Counter = Counter()
    rback: Counter = Counter()
    for it in recent:
        rfront.update(it["front"])
        rback.update(it["back"])
    front_recent_freq = {i: rfront.get(i, 0) for i in range(fmin, fmax + 1)}
    back_recent_freq = {i: rback.get(i, 0) for i in range(bmin, bmax + 1)}

    # 热号 / 冷号（按总体频率）
    def hot_cold(freq: dict[int, int], top: int = 10):
        items = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
        hot = items[:top]
        min_v = min(freq.values())
        cold = [(k, v) for k, v in items if v == min_v][:top]
        return hot, cold

    front_hot, front_cold = hot_cold(front_freq)
    back_hot, back_cold = hot_cold(back_freq)

    # 遗漏：当前连续未出现期数 + 历史最大遗漏
    def omission_per(issue_sets: list[set[int]], pmin: int, pmax: int):
        cur = {i: 0 for i in range(pmin, pmax + 1)}
        mx = {i: 0 for i in range(pmin, pmax + 1)}
        for s in issue_sets:
            for i in range(pmin, pmax + 1):
                if i in s:
                    cur[i] = 0
                else:
                    cur[i] += 1
                    if cur[i] > mx[i]:
                        mx[i] = cur[i]
        return cur, mx

    front_sets = [set(it["front"]) for it in issues]
    back_sets = [set(it["back"]) for it in issues]
    front_cur_omit, front_max_omit = omission_per(front_sets, fmin, fmax)
    back_cur_omit, back_max_omit = omission_per(back_sets, bmin, bmax)

    # 奇偶比例（前区）
    odd_even_dist: Counter = Counter()
    for it in issues:
        odd = sum(1 for x in it["front"] if x % 2 == 1)
        odd_even_dist[f"奇{odd}:偶{5 - odd}"] += 1

    # 大小比例（前区，分界 18：1-17 小，18-35 大）
    boundary = 18
    big_small_dist: Counter = Counter()
    for it in issues:
        big = sum(1 for x in it["front"] if x >= boundary)
        big_small_dist[f"大{big}:小{5 - big}"] += 1

    # 连号概率（前区存在相邻差 1 的对）
    consec_issues = 0
    consec_pairs_total = 0
    for it in issues:
        f = sorted(it["front"])
        pairs = sum(1 for i in range(len(f) - 1) if f[i + 1] - f[i] == 1)
        if pairs > 0:
            consec_issues += 1
        consec_pairs_total += pairs
    consec_prob = consec_issues / n if n else 0.0
    consec_avg = consec_pairs_total / n if n else 0.0

    # 区间分布
    def zone_dist(pool: list[int], pmin: int, pmax: int, zones: int):
        size = (pmax - pmin + 1) // zones
        counter = [0] * zones
        labels = [f"{pmin + i * size}-{pmin + (i + 1) * size - 1}" for i in range(zones)]
        for x in pool:
            idx = min((x - pmin) // size, zones - 1)
            counter[idx] += 1
        return labels, counter

    front_pool = [x for it in issues for x in it["front"]]
    back_pool = [x for it in issues for x in it["back"]]
    front_zone_labels, front_zone_counter = zone_dist(front_pool, fmin, fmax, a["front_zones"])
    back_zone_labels, back_zone_counter = zone_dist(back_pool, bmin, bmax, a["back_zones"])

    return {
        "count": n,
        "front_min": fmin, "front_max": fmax,
        "back_min": bmin, "back_max": bmax,
        "front_freq": front_freq,
        "back_freq": back_freq,
        "front_recent_freq": front_recent_freq,
        "back_recent_freq": back_recent_freq,
        "front_hot": front_hot, "front_cold": front_cold,
        "back_hot": back_hot, "back_cold": back_cold,
        "front_cur_omit": front_cur_omit,
        "front_max_omit": front_max_omit,
        "back_cur_omit": back_cur_omit,
        "back_max_omit": back_max_omit,
        "odd_even_dist": dict(odd_even_dist),
        "big_small_dist": dict(big_small_dist),
        "consec_prob": consec_prob,
        "consec_avg": consec_avg,
        "front_zone_labels": front_zone_labels,
        "front_zone_counter": front_zone_counter,
        "back_zone_labels": back_zone_labels,
        "back_zone_counter": back_zone_counter,
    }
