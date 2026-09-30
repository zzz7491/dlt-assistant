# -*- coding: utf-8 -*-
"""
Task 17.2 Phase 3: 回测引擎实施
只增加实验能力，不改变生产推荐逻辑
"""

import sys
import os
import json
import math
import random
import itertools
from datetime import datetime
from typing import Any, Dict, List, Tuple

# 项目路径设置
PROJECT_ROOT = r'C:\工作空间\dlt\dlt-assistant'
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

# 导入必要模块
from analyzer import (
    analyze, analyze_previous_overlap, analyze_number_temperature,
    analyze_missing_cycle, analyze_structure_distribution, analyze_sum_span
)
from recommender import STRATEGY_LABELS
from scorer import calculate_number_score, calculate_combination_score, normalize_score
from database import load as load_db

# 常量定义
FRONT_MIN, FRONT_MAX = 1, 35
BACK_MIN, BACK_MAX = 1, 12
FRONT_BOUNDARY = 18
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'reports', 'backtest_rolling')


def build_stats(hist: List[Dict]) -> Dict[str, Any]:
    """构建C-1四因素统计 + prev_issue"""
    return {
        "overlap": analyze_previous_overlap(hist),
        "temperature": analyze_number_temperature(hist),
        "missing_cycle": analyze_missing_cycle(hist),
        "structure": analyze_structure_distribution(hist),
        "sum_span": analyze_sum_span(hist),
        "prev_issue": hist[-1] if hist else None,
    }


def strategy_A(analysis: Dict, cfg: Dict, rng: random.Random) -> Dict:
    """A策略：均衡统计型"""
    fmin, fmax = analysis["front_min"], analysis["front_max"]
    hot = [k for k, _ in analysis["front_hot"]]
    cold = [k for k, _ in analysis["front_cold"]]
    
    # 简化的权重计算
    w = {}
    for i in range(fmin, fmax + 1):
        base = analysis.get("front_freq", {}).get(i, 0)
        recent = analysis.get("front_recent_freq", {}).get(i, 0)
        w[i] = 0.5 * base + 0.5 * recent
    
    front = set()
    if hot:
        front |= set(rng.sample(hot, min(2, len(hot))))
    if cold:
        front |= set(rng.sample(cold, min(2, len(cold))))
    
    while len(front) < 5:
        pool = list(range(fmin, fmax + 1))
        weights = [w.get(x, 0) for x in pool]
        chosen = rng.choices(pool, weights=weights, k=1)[0]
        front.add(chosen)
    
    # 奇偶/大小平衡
    for _ in range(30):
        odd = sum(1 for x in front if x % 2 == 1)
        big = sum(1 for x in front if x >= FRONT_BOUNDARY)
        if odd in (2, 3) and big in (2, 3):
            break
        cand = list(front)
        rng.shuffle(cand)
        swapped = False
        if odd > 3 or odd < 2:
            for rm in cand:
                opp = [x for x in range(fmin, fmax+1) if x not in front and (x%2) != (rm%2)]
                if opp:
                    front.discard(rm)
                    front.add(rng.choice(opp))
                    swapped = True
                    break
        elif big > 3 or big < 2:
            for rm in cand:
                opp = [x for x in range(fmin, fmax+1) if x not in front and (x>=FRONT_BOUNDARY) != (rm>=FRONT_BOUNDARY)]
                if opp:
                    front.discard(rm)
                    front.add(rng.choice(opp))
                    swapped = True
                    break
        if not swapped:
            break
    
    # 后区
    bmin, bmax = analysis["back_min"], analysis["back_max"]
    bbase = {k: v/sum(analysis.get("back_freq", {}).values()) for k, v in analysis.get("back_freq", {}).items()}
    brec = {k: v/sum(analysis.get("back_recent_freq", {}).values()) for k, v in analysis.get("back_recent_freq", {}).items()}
    bw = {k: 0.5*bbase.get(k, 0) + 0.5*brec.get(k, 0) for k in range(bmin, bmax+1)}
    back = sorted(rng.sample(list(range(bmin, bmax+1)), 2))
    
    return {"front": sorted(front), "back": back}


def strategy_B(analysis: Dict, cfg: Dict, rng: random.Random) -> Dict:
    """B策略：冷热组合型"""
    fmin, fmax = analysis["front_min"], analysis["front_max"]
    hot = [k for k, _ in analysis["front_hot"]]
    cold = [k for k, _ in analysis["front_cold"]]
    
    front = set()
    if hot:
        front |= set(rng.sample(hot, min(3, len(hot))))
    if cold:
        front |= set(rng.sample(cold, min(2, len(cold))))
    
    while len(front) < 5:
        front.add(rng.choice(list(range(fmin, fmax + 1))))
    
    bmin, bmax = analysis["back_min"], analysis["back_max"]
    back = sorted(rng.sample(list(range(bmin, bmax+1)), 2))
    
    return {"front": sorted(front), "back": back}


def strategy_C(analysis: Dict, cfg: Dict, rng: random.Random) -> Dict:
    """C策略：纯随机型"""
    fmin, fmax = analysis["front_min"], analysis["front_max"]
    bmin, bmax = analysis["back_min"], analysis["back_max"]
    return {
        "front": sorted(rng.sample(range(fmin, fmax + 1), 5)),
        "back": sorted(rng.sample(range(bmin, bmax + 1), 2)),
    }


def strategy_D(stats: Dict, cfg: Dict) -> Dict:
    """D策略：综合评分型（内联实现）"""
    w_cfg = cfg.get("recommend", {}).get("weights", {})
    num_w = w_cfg.get("number", {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15})
    combo_w = w_cfg.get("combo", {})
    svc = w_cfg.get("single_vs_combo", {"single": 0.7, "combo": 0.3})
    w_single = float(svc.get("single", 0.7))
    w_combo = float(svc.get("combo", 0.3))
    top_front = int(w_cfg.get("top_front", 15))
    top_back = int(w_cfg.get("top_back", 8))
    
    temperature = stats.get("temperature", {})
    missing_cycle = stats.get("missing_cycle", {})
    overlap = stats.get("overlap")
    structure = stats.get("structure")
    sum_span = stats.get("sum_span")
    prev_issue = stats.get("prev_issue") or {}
    prev_front = prev_issue.get("front", [])
    prev_back = prev_issue.get("back", [])
    prev_front_set = set(prev_front)
    prev_back_set = set(prev_back)
    
    def pool_scores(pmin: int, pmax: int, kind: str) -> List[Dict]:
        scored = []
        for n in range(pmin, pmax + 1):
            s = calculate_number_score(
                n,
                (temperature.get(kind) or {}).get(n, {}),
                (missing_cycle.get(kind) or {}).get(n, {}),
                overlap,
                is_previous=(n in prev_front_set) if kind == "front" else (n in prev_back_set),
                weights=num_w,
            )
            scored.append(s)
        scored.sort(key=lambda x: x["score_total"], reverse=True)
        return scored
    
    front_top = pool_scores(FRONT_MIN, FRONT_MAX, "front")[:top_front]
    back_top = pool_scores(BACK_MIN, BACK_MAX, "back")[:top_back]
    
    if not front_top or not back_top:
        return {"front": [], "back": [], "model_version": "C-2-D-v1", "score_total": 0.0, "factors": {}, "basis": {}}
    
    fnums = [s["number"] for s in front_top]
    bnums = [s["number"] for s in back_top]
    fmap = {s["number"]: s["score_total"] for s in front_top}
    bmap = {s["number"]: s["score_total"] for s in back_top}
    ffactors = {s["number"]: s["factors"] for s in front_top}
    bfactors = {s["number"]: s["factors"] for s in back_top}
    
    cache = {}
    def structure_score(combo):
        front, back = combo["front"], combo["back"]
        kf = len(set(front) & prev_front_set)
        kb = len(set(back) & prev_back_set)
        odd = sum(1 for x in front if x % 2 == 1)
        big = sum(1 for x in front if x >= FRONT_BOUNDARY)
        size = (FRONT_MAX - FRONT_MIN + 1) // 5
        zl = sorted((x - FRONT_MIN) // size for x in front)
        key = (kf, kb, odd, big, tuple(zl), sum(front))
        if key not in cache:
            r = calculate_combination_score(combo, overlap, structure, sum_span, prev_front, prev_back, weights=combo_w)
            cache[key] = (r["score_total"], r["factors"])
        return cache[key]
    
    scored_combos = []
    for fc in itertools.combinations(fnums, 5):
        for bc in itertools.combinations(bnums, 2):
            combo = {"front": list(fc), "back": list(bc)}
            cs_struct, cs_factors = structure_score(combo)
            avg_single = (sum(fmap[n] for n in fc) + sum(bmap[n] for n in bc)) / 7.0
            total = normalize_score(w_single * avg_single + w_combo * cs_struct)
            scored_combos.append((total, combo, cs_factors))
    
    scored_combos.sort(key=lambda x: (-x[0], x[1]["front"], x[1]["back"]))
    total, combo, cs_factors = scored_combos[0]
    
    def mean_factor(key):
        vals = [ffactors[n][key] for n in combo["front"]] + [bfactors[n][key] for n in combo["back"]]
        return round(sum(vals) / len(vals), 2) if vals else 0.0
    
    return {
        "front": combo["front"],
        "back": combo["back"],
        "model_version": "C-2-D-v1",
        "score_total": total,
        "factors": cs_factors,
        "basis": {
            "heat": mean_factor("heat"),
            "missing": mean_factor("missing"),
            "trend": mean_factor("trend"),
            "inherit": mean_factor("inherit"),
            "structure": cs_factors,
        },
    }


def run_single_period(t: int, issues: List[Dict], cfg: Dict) -> Dict[str, Any]:
    """单期回测：用issues[:t]预测issues[t]"""
    hist = issues[:t]
    stats = build_stats(hist)
    analysis = analyze(hist, cfg)
    
    real = issues[t]
    rf = set(real.get("front") or [])
    rb = set(real.get("back") or [])
    
    result = {
        "issue": real.get("issue"),
        "date": real.get("date"),
        "actual_front": list(real.get("front", [])),
        "actual_back": list(real.get("back", [])),
        "strategies": {},
        "random_baseline": None,
    }
    
    # 生成各策略推荐
    rng = random.Random(42)
    
    # A策略
    rec_a = strategy_A(analysis, cfg, rng)
    fh_a = len(set(rec_a.get("front") or []) & rf)
    bh_a = len(set(rec_a.get("back") or []) & rb)
    result["strategies"]["A"] = {"front_hit": fh_a, "back_hit": bh_a, "total_hit": fh_a+bh_a, 
                                 "front": rec_a.get("front",[]), "back": rec_a.get("back",[])}
    
    # B策略
    rec_b = strategy_B(analysis, cfg, rng)
    fh_b = len(set(rec_b.get("front") or []) & rf)
    bh_b = len(set(rec_b.get("back") or []) & rb)
    result["strategies"]["B"] = {"front_hit": fh_b, "back_hit": bh_b, "total_hit": fh_b+bh_b,
                                 "front": rec_b.get("front",[]), "back": rec_b.get("back",[])}
    
    # C策略
    rec_c = strategy_C(analysis, cfg, rng)
    fh_c = len(set(rec_c.get("front") or []) & rf)
    bh_c = len(set(rec_c.get("back") or []) & rb)
    result["strategies"]["C"] = {"front_hit": fh_c, "back_hit": bh_c, "total_hit": fh_c+bh_c,
                                 "front": rec_c.get("front",[]), "back": rec_c.get("back",[])}
    
    # D策略
    d_rec = strategy_D(stats, cfg)
    d_fh = len(set(d_rec.get("front") or []) & rf)
    d_bh = len(set(d_rec.get("back") or []) & rb)
    result["strategies"]["D"] = {
        "front_hit": d_fh,
        "back_hit": d_bh,
        "total_hit": d_fh + d_bh,
        "front": d_rec.get("front", []),
        "back": d_rec.get("back", []),
        "score_total": d_rec.get("score_total"),
        "basis": d_rec.get("basis", {}),
    }
    
    # 随机基准
    rng_rand = random.Random(t * 7 + 3)
    rand_front = sorted(rng_rand.sample(range(FRONT_MIN, FRONT_MAX + 1), 5))
    rand_back = sorted(rng_rand.sample(range(BACK_MIN, BACK_MAX + 1), 2))
    rand_fh = len(set(rand_front) & rf)
    rand_bh = len(set(rand_back) & rb)
    result["random_baseline"] = {
        "front_hit": rand_fh,
        "back_hit": rand_bh,
        "total_hit": rand_fh + rand_bh,
        "front": rand_front,
        "back": rand_back,
    }
    
    # 组合质量指标
    result["quality"] = analyze_combo_quality(result["strategies"]["D"], real)
    
    return result


def analyze_combo_quality(combo: Dict, actual: Dict) -> Dict[str, Any]:
    """分析组合质量指标"""
    front = combo.get("front", [])
    back = combo.get("back", [])
    
    if not front:
        return {"front_sum": 0, "span": 0, "odd_count": 0, "big_count": 0,
                "consec_pairs": 0, "max_consecutive": 0, "is_extreme": False}
    
    # 和值分析
    front_sum = sum(front)
    span = max(front) - min(front) if front else 0
    
    # 奇偶分析
    odd_count = sum(1 for x in front if x % 2 == 1)
    big_count = sum(1 for x in front if x >= FRONT_BOUNDARY)
    
    # 连号分析
    sorted_front = sorted(front)
    consec_pairs = sum(1 for i in range(len(sorted_front)-1) if sorted_front[i+1] - sorted_front[i] == 1)
    max_consec = 1
    current_consec = 1
    for i in range(1, len(sorted_front)):
        if sorted_front[i] - sorted_front[i-1] == 1:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 1
    
    # 判断是否极端
    is_extreme = max_consec >= 4 or front_sum < 60 or front_sum > 140
    
    return {
        "front_sum": front_sum,
        "span": span,
        "odd_count": odd_count,
        "big_count": big_count,
        "consec_pairs": consec_pairs,
        "max_consecutive": max_consec,
        "is_extreme": is_extreme,
    }


def calc_strategy_stats(periods: List[Dict]) -> Dict:
    """计算策略统计指标"""
    if not periods:
        return {"count": 0}
    fh = [p["front_hit"] for p in periods]
    bh = [p["back_hit"] for p in periods]
    th = [p["total_hit"] for p in periods]
    dist = {}
    for t in th:
        key = str(t)
        dist[key] = dist.get(key, 0) + 1
    return {
        "count": len(periods),
        "avg_front_hit": round(sum(fh) / len(fh), 4),
        "avg_back_hit": round(sum(bh) / len(bh), 4),
        "avg_total_hit": round(sum(th) / len(th), 4),
        "max_total_hit": max(th),
        "hit_distribution": dist,
    }


def calc_random_baseline() -> Dict:
    """理论随机基准期望值"""
    exp_front = 5 * 5 / 35  # 0.7143
    exp_back = 2 * 2 / 12   # 0.3333
    return {
        "expected_front_hit": round(exp_front, 4),
        "expected_back_hit": round(exp_back, 4),
        "expected_total_hit": round(exp_front + exp_back, 4),
    }


def analyze_factors(periods: List[Dict]) -> Dict:
    """因子贡献分析"""
    d_rows = [p for p in periods if "strategies" in p and "D" in p["strategies"] and p["strategies"]["D"].get("basis")]
    if not d_rows:
        return {"note": "No D strategy data"}
    
    factors_data = {"heat": [], "missing": [], "trend": [], "inherit": [], "structure": []}
    for r in d_rows:
        basis = r["strategies"]["D"].get("basis", {})
        total_hit = r["strategies"]["D"]["total_hit"]
        for f in factors_data:
            v = basis.get(f)
            if isinstance(v, (int, float)):
                factors_data[f].append((v, total_hit))
            elif isinstance(v, dict) and f == "structure":
                vals = [x for x in v.values() if isinstance(x, (int, float))]
                if vals:
                    factors_data[f].append((sum(vals) / len(vals), total_hit))
    
    results = {}
    for factor, data in factors_data.items():
        if len(data) < 10:
            results[factor] = {"count": len(data), "note": "Insufficient samples"}
            continue
        data.sort(key=lambda x: x[0])
        mid = len(data) // 2
        low_hits = [h for _, h in data[:mid]]
        high_hits = [h for _, h in data[mid:]]
        avg_low = sum(low_hits) / len(low_hits)
        avg_high = sum(high_hits) / len(high_hits)
        
        xs = [d[0] for d in data]
        ys = [d[1] for d in data]
        mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
        cov = sum((x-mx)*(y-my) for x,y in data)/len(data)
        sx = math.sqrt(sum((x-mx)**2 for x in xs)/len(xs))
        sy = math.sqrt(sum((y-my)**2 for y in ys)/len(ys))
        corr = cov/(sx*sy) if sx>0 and sy>0 else 0
        
        results[factor] = {
            "count": len(data),
            "avg_value_low": round(avg_low, 4),
            "avg_value_high": round(avg_high, 4),
            "avg_hit_low": round(avg_low, 4),
            "avg_hit_high": round(avg_high, 4),
            "lift_when_high": round(avg_high - avg_low, 4),
            "correlation_with_hit": round(corr, 4),
        }
    return results


def analyze_quality_metrics(periods: List[Dict]) -> Dict:
    """分析组合质量指标"""
    if not periods:
        return {}
    
    metrics = {
        "sum_in_range": [],
        "span_in_range": [],
        "odd_even_valid": [],
        "extreme_avoidance": [],
    }
    
    # 默认阈值（可根据实际数据调整）
    sum_p25, sum_p75 = 90, 120
    span_p25, span_p75 = 20, 35
    
    for p in periods:
        q = p.get("quality", {})
        metrics["sum_in_range"].append(sum_p25 <= q.get("front_sum", 0) <= sum_p75)
        metrics["span_in_range"].append(span_p25 <= q.get("span", 0) <= span_p75)
        metrics["odd_even_valid"].append(q.get("odd_count", 0) in [2, 3])
        metrics["extreme_avoidance"].append(not q.get("is_extreme", False))
    
    def rate(lst):
        return sum(lst) / len(lst) if lst else 0
    
    return {
        "sum_in_range_rate": round(rate(metrics["sum_in_range"]), 4),
        "span_in_range_rate": round(rate(metrics["span_in_range"]), 4),
        "odd_even_valid_rate": round(rate(metrics["odd_even_valid"]), 4),
        "extreme_avoidance_rate": round(rate(metrics["extreme_avoidance"]), 4),
    }


def run_full_backtest(issues: List[Dict], window_sizes: List[int] = None, 
                      output_dir: str = OUTPUT_DIR) -> Dict:
    """完整滚动回测主流程"""
    cfg = {
        "recommend": {
            "weights": {
                "number": {"heat": 0.30, "missing": 0.30, "trend": 0.25, "inherit": 0.15},
                "combo": {"inherit_match": 0.20, "odd_even_match": 0.20, "big_small_match": 0.20, 
                          "zone_match": 0.20, "sum_span_match": 0.20},
                "single_vs_combo": {"single": 0.7, "combo": 0.3},
                "top_front": 15, "top_back": 8,
            }
        },
        "analysis": {"front_min": 1, "front_max": 35, "back_min": 1, "back_max": 12,
                     "front_zones": 5, "back_zones": 2, "recent_window": 50}
    }
    
    issues = sorted(issues, key=lambda x: x["issue"])
    n_issues = len(issues)
    windows = window_sizes or [100, 300, 500]
    random_baseline = calc_random_baseline()
    
    all_results = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_issues": n_issues,
        "issue_range": f"{issues[0]['issue']}-{issues[-1]['issue']}",
        "random_baseline": random_baseline,
        "windows": {},
    }
    
    os.makedirs(output_dir, exist_ok=True)
    
    for window in windows:
        start = n_issues - window
        if start < 100:
            start = 100
        end = n_issues - 1
        
        print(f"\n[*] {window}-period window: t={start}~{end} ({end-start+1} periods)")
        
        rows = []
        for t in range(start, end + 1):
            row = run_single_period(t, issues, cfg)
            rows.append(row)
            if (t - start) % 50 == 0:
                d = row["strategies"]["D"]
                print(f"    t={t} issue={row['issue']} D_hit={d['total_hit']}")
        
        # 汇总各策略
        strategy_data = {"A": [], "B": [], "C": [], "D": [], "random": []}
        for r in rows:
            for s in ("A", "B", "C", "D"):
                if s in r.get("strategies", {}):
                    strategy_data[s].append(r["strategies"][s])
            if r.get("random_baseline"):
                strategy_data["random"].append(r["random_baseline"])
        
        strat_stats = {s: calc_strategy_stats(strategy_data[s]) for s in strategy_data}
        
        # vs_random对比
        vs_random = {}
        for s in ("A", "B", "C", "D"):
            ss = strat_stats[s]
            if ss["count"] > 0:
                rs = random_baseline
                vs_random[s] = {
                    "front_lift_pct": round((ss["avg_front_hit"] - rs["expected_front_hit"]) / rs["expected_front_hit"] * 100, 2),
                    "back_lift_pct": round((ss["avg_back_hit"] - rs["expected_back_hit"]) / rs["expected_back_hit"] * 100, 2),
                    "total_lift_pct": round((ss["avg_total_hit"] - rs["expected_total_hit"]) / rs["expected_total_hit"] * 100, 2),
                }
        
        factor_analysis = analyze_factors(rows)
        quality_metrics = analyze_quality_metrics(rows)
        
        # 保存逐期记录
        period_file = os.path.join(output_dir, f"periods_{window}.jsonl")
        with open(period_file, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        
        all_results["windows"][str(window)] = {
            "summary": {
                "n": len(rows),
                "start_issue": rows[0]["issue"],
                "end_issue": rows[-1]["issue"],
                "strategies": strat_stats,
                "vs_random": vs_random,
            },
            "factor_analysis": factor_analysis,
            "quality_metrics": quality_metrics,
            "periods_file": period_file,
        }
        
        print(f"    [OK] Completed {len(rows)} periods")
    
    # 保存总览
    summary_file = os.path.join(output_dir, "summary_all_windows.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    return all_results


def generate_report(results: Dict, output_path: str):
    """生成Markdown格式的实验报告"""
    lines = []
    lines.append("# Task 17.2 Phase 3 回测实验报告")
    lines.append("")
    lines.append(f"**日期：** {results.get('update_time', 'N/A')}")
    lines.append(f"**数据范围：** {results.get('issue_range', 'N/A')}")
    lines.append(f"**总期数：** {results.get('total_issues', 0)}")
    lines.append("")
    
    lines.append("## 一、各窗口回测结果对比")
    lines.append("")
    lines.append("| 指标 | 100期 | 300期 | 500期 |")
    lines.append("|------|-------|-------|-------|")
    
    windows = results.get('windows', {})
    for metric in ['avg_front_hit', 'avg_back_hit', 'avg_total_hit']:
        row = f"| {metric} |"
        for w in [100, 300, 500]:
            w_key = str(w)
            if w_key in windows:
                d = windows[w_key].get('summary', {}).get('strategies', {}).get('D', {})
                val = d.get(metric, 'N/A')
                row += f" {val:.4f} |"
            else:
                row += " N/A |"
        lines.append(row)
    
    lines.append("")
    lines.append("## 二、策略 vs 随机基准对比")
    lines.append("")
    lines.append("| 策略 | 前区提升 | 后区提升 | 总命中提升 |")
    lines.append("|------|----------|----------|------------|")
    
    for w in [100, 300, 500]:
        w_key = str(w)
        if w_key not in windows:
            continue
        vs_random = windows[w_key].get('summary', {}).get('vs_random', {})
        for s in ['A', 'B', 'C', 'D']:
            if s in vs_random:
                vr = vs_random[s]
                lines.append(f"| {w_key}期-{s} | {vr.get('front_lift_pct', 0):+.1f}% | {vr.get('back_lift_pct', 0):+.1f}% | {vr.get('total_lift_pct', 0):+.1f}% |")
    
    lines.append("")
    lines.append("## 三、因子贡献分析（300期窗口）")
    lines.append("")
    
    w300 = windows.get('300', {})
    factor_analysis = w300.get('factor_analysis', {})
    
    if factor_analysis and 'note' not in factor_analysis:
        lines.append("| 因子 | 样本数 | 低组均命中 | 高组均命中 | 提升幅度 | 相关系数 |")
        lines.append("|------|--------|-----------|-----------|----------|----------|")
        for f, data in factor_analysis.items():
            if isinstance(data, dict) and 'count' in data:
                lines.append(f"| {f} | {data.get('count', 0)} | {data.get('avg_hit_low', 0):.4f} | {data.get('avg_hit_high', 0):.4f} | {data.get('lift_when_high', 0):+.4f} | {data.get('correlation_with_hit', 0):.4f} |")
    else:
        lines.append("因子分析数据不足或无 D 策略记录。")
    
    lines.append("")
    lines.append("## 四、组合质量指标")
    lines.append("")
    
    for w in [100, 300, 500]:
        w_key = str(w)
        if w_key not in windows:
            continue
        qm = windows[w_key].get('quality_metrics', {})
        lines.append(f"### {w}期窗口")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        for k, v in qm.items():
            lines.append(f"| {k} | {v:.4f} |")
        lines.append("")
    
    lines.append("## 五、核心问题回答")
    lines.append("")
    
    # 问题1：D策略是否超过随机？
    lines.append("### 5.1 当前D策略是否超过随机？")
    lines.append("")
    d_300 = windows.get('300', {}).get('summary', {}).get('strategies', {}).get('D', {})
    random_300 = windows.get('300', {}).get('summary', {}).get('strategies', {}).get('random', {})
    if d_300.get('count', 0) > 0 and random_300.get('count', 0) > 0:
        d_lift = d_300.get('avg_total_hit', 0) - random_300.get('avg_total_hit', 0)
        conclusion = "✅ **是**，D策略平均命中比随机高 {:.2f} 个号码".format(d_lift) if d_lift > 0 else "❌ **否**，D策略未明显超过随机"
        lines.append(conclusion)
    else:
        lines.append("数据不足，无法判断")
    lines.append("")
    
    # 问题2：哪些因素贡献有效？
    lines.append("### 5.2 哪些因素贡献有效？")
    lines.append("")
    if factor_analysis and 'note' not in factor_analysis:
        effective = [f for f, data in factor_analysis.items() 
                     if isinstance(data, dict) and data.get('correlation_with_hit', 0) > 0.1]
        if effective:
            lines.append(f"有效因素（相关系数>0.1）：{', '.join(effective)}")
        else:
            lines.append("无明显有效因素")
    lines.append("")
    
    # 问题3：哪些规则只是降低极端组合？
    lines.append("### 5.3 哪些规则只是降低极端组合，没有提高命中？")
    lines.append("")
    lines.append("基于现有数据，需要进一步实验验证。建议：")
    lines.append("1. 对比带过滤vs不带过滤的组合命中率")
    lines.append("2. 分析各过滤规则的独立贡献")
    lines.append("")
    
    # 问题4：是否值得实施组合优化模型？
    lines.append("### 5.4 下一步是否值得实施组合优化模型？")
    lines.append("")
    if d_300.get('count', 0) > 0:
        if d_lift > 0:
            lines.append("✅ **建议实施**。D策略已显示超过随机的潜力，组合优化可进一步提升。")
        else:
            lines.append("⚠️ **谨慎实施**。当前D策略未明显优于随机，需先优化基础模型。")
    lines.append("")
    
    lines.append("---")
    lines.append("*本报告仅为娱乐分析用途，不构成任何购彩建议*")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    print("=" * 60)
    print("Task 17.2 Phase 3: Rolling Backtest Engine Implementation")
    print("=" * 60)
    
    # 加载数据
    db_path = os.path.join(PROJECT_ROOT, "data", "dlt_history.json")
    print(f"\n[1] Loading historical data...")
    db = load_db(db_path)
    issues = db.get("issues", [])
    print(f"    [OK] Loaded {len(issues)} periods ({issues[0]['issue']}-{issues[-1]['issue']})")
    
    # 运行回测
    print("\n[2] Running rolling backtest...")
    results = run_full_backtest(issues, window_sizes=[100, 300, 500])
    
    # 打印汇总
    print("\n[3] Results Summary:")
    print("-" * 60)
    for window, data in results.get("windows", {}).items():
        summary = data.get("summary", {})
        print(f"\n=== {window}-period window ({summary.get('n',0)} periods) ===")
        print(f"  {'Strategy':<8} {'AvgFront':<10} {'AvgBack':<10} {'AvgTotal':<10} {'VsRandom':<10}")
        print(f"  {'-'*50}")
        for s in ["A", "B", "C", "D", "random"]:
            ss = summary.get("strategies", {}).get(s, {})
            if ss.get("count", 0) > 0:
                vr = summary.get("vs_random", {}).get(s, {})
                lift = vr.get("total_lift_pct", 0) if s != "random" else 0
                print(f"  {s:<8} {ss['avg_front_hit']:.4f}     {ss['avg_back_hit']:.4f}      {ss['avg_total_hit']:.4f}     {lift:+.1f}%")
        
        # 质量指标
        qm = data.get("quality_metrics", {})
        if qm:
            print(f"\n  Quality Metrics:")
            for k, v in qm.items():
                print(f"    {k}: {v:.4f}")
    
    # 生成报告
    report_file = os.path.join(PROJECT_ROOT, "Task17.2-Phase3-回测实验报告.md")
    generate_report(results, report_file)
    
    print(f"\n[4] Report saved to: {report_file}")
    print("\nDone!")
