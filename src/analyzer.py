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


# =========================================================
# C-1 多因素模型基础统计（只新增，不接入 analyze()/recommend()）
# 独立纯函数，仅服务后续 C-2 推荐模型；不改变现有输出与推荐结果。
# =========================================================


def analyze_previous_overlap(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """上期号码继承统计（仅历史分布描述，不预测具体重复号码）。

    输入：issues（任意长度，≥2 期才有分布）。
    输出：前/后区与上一期重复数量分布（概率 0-1）+ 期望重复个数。
    """
    seq = sorted(issues, key=lambda x: x["issue"])
    n = len(seq)
    fd: Counter = Counter()
    bd: Counter = Counter()
    for i in range(1, n):
        pf = set(seq[i - 1].get("front") or [])
        pb = set(seq[i - 1].get("back") or [])
        cf = set(seq[i].get("front") or [])
        cb = set(seq[i].get("back") or [])
        fd[len(pf & cf)] += 1
        bd[len(pb & cb)] += 1
    pairs = max(n - 1, 1)
    fdist = {str(k): round(fd.get(k, 0) / pairs, 6) for k in range(0, 6)}
    bdist = {str(k): round(bd.get(k, 0) / pairs, 6) for k in range(0, 3)}
    exp_f = sum(k * fd.get(k, 0) for k in range(6)) / pairs
    exp_b = sum(k * bd.get(k, 0) for k in range(3)) / pairs
    return {
        "front_overlap_distribution": fdist,
        "back_overlap_distribution": bdist,
        "expected_front_overlap": round(exp_f, 4),
        "expected_back_overlap": round(exp_b, 4),
    }


def analyze_number_temperature(issues: list[dict[str, Any]],
                               front_min: int = 1, front_max: int = 35,
                               back_min: int = 1, back_max: int = 12) -> dict[str, Any]:
    """号码冷热统计：总频 / 近30期 / 近100期 / 趋势。

    trend = 近30期每期频率 − 近100期每期频率（正值=近期升温，负值=降温）。
    输出：{"front": {num: {...}}, "back": {num: {...}}}。
    """
    seq = sorted(issues, key=lambda x: x["issue"])
    n = len(seq)

    def calc(pmin: int, pmax: int, key: str) -> dict:
        total: Counter = Counter()
        r30: Counter = Counter()
        r100: Counter = Counter()
        for i, it in enumerate(seq):
            total.update(it.get(key) or [])
            if i >= n - 30:
                r30.update(it.get(key) or [])
            if i >= n - 100:
                r100.update(it.get(key) or [])
        w30 = min(30, n)
        w100 = min(100, n)
        out: dict[int, dict] = {}
        for num in range(pmin, pmax + 1):
            trend = round((r30.get(num, 0) / w30 if w30 else 0) - (r100.get(num, 0) / w100 if w100 else 0), 4)
            out[num] = {
                "total_count": total.get(num, 0),
                "recent_30": r30.get(num, 0),
                "recent_100": r100.get(num, 0),
                "trend": trend,
            }
        return out

    return {"front": calc(front_min, front_max, "front"), "back": calc(back_min, back_max, "back")}


def analyze_missing_cycle(issues: list[dict[str, Any]],
                          front_min: int = 1, front_max: int = 35,
                          back_min: int = 1, back_max: int = 12) -> dict[str, Any]:
    """遗漏周期统计：当前遗漏 / 平均遗漏（周期均值）/ 最大遗漏 / 周期状态。

    cycle_status：
      just_hit     当前遗漏 0（最新一期开出）
      within_cycle 当前遗漏 ≤ 平均周期（周期内）
      over_avg     当前遗漏 > 平均周期 且 < 历史最大（回补观察窗口）
      at_max       当前遗漏 ≥ 历史最大
    输出：{"front": {num: {...}}, "back": {num: {...}}}。
    """
    seq = sorted(issues, key=lambda x: x["issue"])

    def calc(pmin: int, pmax: int, key: str) -> dict:
        out: dict[int, dict] = {}
        for num in range(pmin, pmax + 1):
            cur = 0
            for i in range(len(seq) - 1, -1, -1):
                if num in (seq[i].get(key) or []):
                    break
                cur += 1
            runs: list[int] = []
            run = 0
            for it in seq:
                if num in (it.get(key) or []):
                    if run:
                        runs.append(run)
                        run = 0
                else:
                    run += 1
            if run:
                runs.append(run)
            avg = round(sum(runs) / len(runs), 2) if runs else 0.0
            mx = max(runs) if runs else 0
            if cur == 0:
                status = "just_hit"
            elif avg == 0 or cur <= avg:
                status = "within_cycle"
            elif cur < mx:
                status = "over_avg"
            else:
                status = "at_max"
            out[num] = {"current_missing": cur, "avg_missing": avg, "max_missing": mx, "cycle_status": status}
        return out

    return {"front": calc(front_min, front_max, "front"), "back": calc(back_min, back_max, "back")}


def analyze_structure_distribution(issues: list[dict[str, Any]],
                                   front_min: int = 1, front_max: int = 35,
                                   back_min: int = 1, back_max: int = 12,
                                   front_zones: int = 5, back_zones: int = 2,
                                   boundary: int = 18) -> dict[str, Any]:
    """结构分布统计：奇偶 / 大小 / 连号 / 区间分布（口径与 analyze() 对齐）。

    输出：{"odd_even": {...}, "big_small": {...}, "consecutive": {...},
          "zone_distribution": {"front": {...}, "back": {...}}}。
    """
    seq = sorted(issues, key=lambda x: x["issue"])
    n = len(seq)
    odd_even: Counter = Counter()
    big_small: Counter = Counter()
    consec = 0
    consec_pairs = 0
    fpool = [x for it in seq for x in (it.get("front") or [])]
    bpool = [x for it in seq for x in (it.get("back") or [])]

    def zone_dist(pool: list[int], pmin: int, pmax: int, zones: int) -> dict:
        size = (pmax - pmin + 1) // zones
        counter = [0] * zones
        labels = [f"{pmin + i * size}-{pmin + (i + 1) * size - 1}" for i in range(zones)]
        for x in pool:
            idx = min((x - pmin) // size, zones - 1)
            counter[idx] += 1
        total = len(pool) or 1
        return {"labels": labels, "counts": counter, "pct": [round(c / total, 4) for c in counter]}

    for it in seq:
        fcur = it.get("front") or []
        odd = sum(1 for x in fcur if x % 2 == 1)
        odd_even[f"奇{odd}:偶{5 - odd}"] += 1
        big = sum(1 for x in fcur if x >= boundary)
        big_small[f"大{big}:小{5 - big}"] += 1
        f = sorted(fcur)
        pairs = sum(1 for i in range(len(f) - 1) if f[i + 1] - f[i] == 1)
        if pairs > 0:
            consec += 1
        consec_pairs += pairs

    return {
        "odd_even": dict(odd_even),
        "big_small": dict(big_small),
        "consecutive": {
            "prob": round(consec / n, 4) if n else 0,
            "avg_pairs": round(consec_pairs / n, 4) if n else 0,
        },
        "zone_distribution": {
            "front": zone_dist(fpool, front_min, front_max, front_zones),
            "back": zone_dist(bpool, back_min, back_max, back_zones),
        },
    }


def analyze_sum_span(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """和值/跨度历史分布统计（E-2 新增，纯函数，不生成号码）。

    供 scorer.calculate_combination_score 的 sum_span_stats 使用；
    输出与 scorer 契约一致：
      {"front_sum": {"p25", "p75", "mean"},
       "front_span": {"p25", "p75"},
       "back_span":  {"p25", "p75"}}
    空数据 / 无有效期返回空 dict（scorer 端 lo/hi 缺失 → sum_span_match=中性 50）。
    """
    seq = sorted(issues, key=lambda x: x["issue"])
    fsums: list[int] = []
    fspans: list[int] = []
    bspans: list[int] = []
    for it in seq:
        f = it.get("front") or []
        b = it.get("back") or []
        if len(f) >= 2 and len(b) >= 2:
            fsums.append(sum(f))
            fspans.append(max(f) - min(f))
            bspans.append(max(b) - min(b))
    if not fsums:
        return {}

    def pct(sorted_arr: list[int], p: int) -> int:
        n = len(sorted_arr)
        idx = min(max(0, (n * p) // 100), n - 1)
        return sorted_arr[idx]

    fs = sorted(fsums)
    fp = sorted(fspans)
    bp = sorted(bspans)
    return {
        "front_sum": {
            "p25": pct(fs, 25),
            "p75": pct(fs, 75),
            "mean": round(sum(fs) / len(fs), 2),
        },
        "front_span": {"p25": pct(fp, 25), "p75": pct(fp, 75)},
        "back_span": {"p25": pct(bp, 25), "p75": pct(bp, 75)},
    }

