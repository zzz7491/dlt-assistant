"""P3-3 特征有效性 & 消融评测（research only；不改生产算法/权重/selector/26112）。

科学目标：回答当前推荐系统使用的历史统计特征
（frequency / omission / temperature / overlap / sum / span / odd-even /
 size / structure / risk …）是否具有**严格 OOS** 信息价值。

两层有效性（任务书 STEP 5）：
  LEVEL 1  单号特征：一个号码的 freq/omit/hot/temperature/overlap 是否与
           下一期该号码"出现与否"有关。
  LEVEL 2  候选特征：一个候选组合的 sum/span/odd-even/size/structure/risk
           是否与最终命中数有关。

泄漏契约（STEP 4）：
  对 target t（位置索引），feature(t) 只能使用 issues[:t]。
  target/未来/post-draw/actual-hit 绝不进入特征计算。build_single_features
  内置 leakage assertion。

全部特征值来自真实生产 analyzer/scorer 函数（不复制"类似版"）：
  analyze / analyze_number_temperature / analyze_missing_cycle /
  analyze_previous_overlap / calculate_combination_score。
"""
from __future__ import annotations

import random
from typing import Any

from ..analyzer import (analyze, analyze_number_temperature, analyze_missing_cycle,
                        analyze_previous_overlap, analyze_sum_span,
                        analyze_structure_distribution)
from ..scorer import calculate_combination_score

# ---------------------------------------------------------------- 常量
FRONT_POOL = list(range(1, 36))     # 1-35
BACK_POOL = list(range(1, 13))      # 1-12
RECENT_WINDOW = 50
BOOTSTRAP_SEED = 20260930
BOOTSTRAP_N = 10000
NULL_SEEDS = 50                     # deterministic null-control seeds 0..49
NULL_PERM_N = 2000

# 单号特征列（从生产代码确认；STEP 2 inventory）
SINGLE_FEATURES = [
    "freq_ratio", "recent_ratio", "cur_omit", "max_omit", "avg_omit",
    "omit_ratio", "trend", "hot", "in_prev", "zone",
]


# =========================================================
# LEVEL 1：单号特征构建（生产函数驱动 + 泄漏断言）
# =========================================================

def _front_zone(num: int, zones: int = 5, pmin: int = 1) -> int:
    size = max(1, (35 - pmin + 1) // zones)
    return min((num - pmin) // size, zones - 1)


def _back_zone(num: int, zones: int = 2, pmin: int = 1) -> int:
    size = max(1, (12 - pmin + 1) // zones)
    return min((num - pmin) // size, zones - 1)


def build_single_features(t: int, issues: list[dict], cfg: dict) -> dict[str, Any]:
    """target t（位置）的单号特征 + 出现 label。仅用 issues[:t]。

    返回：
      front: {num(int): {feature: value}}
      back:  {num(int): {feature: value}}
      front_labels / back_labels: {num: 0/1}
    label 来自 issues[t]（target 本身），特征来自 issues[:t]。
    """
    if t < 1:
        raise ValueError("target position t must be >= 1 (needs at least 1 prior draw)")
    target = issues[t]
    evidence = issues[:t]                     # STRICT: only < t
    # --- leakage assertion（STEP 4）：evidence 不得包含 target 或其后
    assert len(evidence) == t, "evidence length must equal t (issues[:t])"
    if evidence:
        assert evidence[-1]["issue"] != target["issue"], "target must not be in evidence"
        # evidence 的最后一期必须严格早于 target（按位置），此处 t 即前 t 期
    prev = issues[t - 1]
    n_ev = len(evidence)

    an = analyze(evidence, cfg)
    temp = analyze_number_temperature(evidence)
    mc = analyze_missing_cycle(evidence)
    recent_w = min(RECENT_WINDOW, n_ev)

    front_hot = {k for k, _ in an.get("front_hot", [])}
    back_hot = {k for k, _ in an.get("back_hot", [])}
    prev_front = set(prev.get("front") or [])
    prev_back = set(prev.get("back") or [])
    target_front = set(target.get("front") or [])
    target_back = set(target.get("back") or [])

    def _features(pool, freq, rfreq, omit, maxomit, hotset, prevset, targetset, zfn, kind):
        out = {}
        for num in pool:
            cur_omit = omit.get(num, 0)
            avg_omit = float(mc[kind][num]["avg_missing"])
            if avg_omit > 0:
                omit_ratio = cur_omit / avg_omit
            else:
                omit_ratio = float(cur_omit) if cur_omit > 0 else 0.0
            out[num] = {
                "freq_ratio": (freq.get(num, 0) / n_ev) if n_ev else 0.0,
                "recent_ratio": (rfreq.get(num, 0) / recent_w) if recent_w else 0.0,
                "cur_omit": cur_omit,
                "max_omit": maxomit.get(num, 0),
                "avg_omit": avg_omit,
                "omit_ratio": omit_ratio,
                "trend": float(temp[kind][num]["trend"]),
                "hot": 1 if num in hotset else 0,
                "in_prev": 1 if num in prevset else 0,
                "zone": zfn(num),
            }
        labels = {num: (1 if num in targetset else 0) for num in pool}
        return out, labels

    front_feats, front_labels = _features(
        FRONT_POOL, an.get("front_freq", {}), an.get("front_recent_freq", {}),
        an.get("front_cur_omit", {}), an.get("front_max_omit", {}),
        front_hot, prev_front, target_front, _front_zone, "front")
    back_feats, back_labels = _features(
        BACK_POOL, an.get("back_freq", {}), an.get("back_recent_freq", {}),
        an.get("back_cur_omit", {}), an.get("back_max_omit", {}),
        back_hot, prev_back, target_back, _back_zone, "back")

    return {
        "t": t,
        "issue": target.get("issue"),
        "front": front_feats,
        "back": back_feats,
        "front_labels": front_labels,
        "back_labels": back_labels,
    }


def _features_to_lists(feats: dict[int, dict], labels: dict[int, int], zone: str):
    """把 {num:{feat:val}} 转成 {feat: [val in pool order]} + label 向量（pool order）。"""
    pool = FRONT_POOL if zone == "front" else BACK_POOL
    data = {f: [feats[num][f] for num in pool] for f in SINGLE_FEATURES}
    lab = [labels[num] for num in pool]
    return data, lab


def pool_single_features(t_idxs: list[int], issues: list[dict], cfg: dict, zone: str):
    """池化多 target 的单号特征（features 来自各 issues[:t]，labels 来自 issues[t]）。

    返回 ({feat: [pooled values]}, [pooled labels])。严格泄漏契约：每个 target 只用 issues[:t]。
    """
    feat = {f: [] for f in SINGLE_FEATURES}
    lab: list[int] = []
    for t in t_idxs:
        s = build_single_features(t, issues, cfg)
        fd, fl = _features_to_lists(s[zone], s[f"{zone}_labels"], zone)
        for f in SINGLE_FEATURES:
            feat[f].extend(fd[f])
        lab.extend(fl)
    return feat, lab


# =========================================================
# 描述性 / 判别度量（stdlib）
# =========================================================

def _ranks(vals: list[float]) -> list[float]:
    n = len(vals)
    order = sorted(range(n), key=lambda i: vals[i])
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def roc_auc(labels: list[int], scores: list[float]) -> float:
    """Mann-Whitney ROC-AUC（对 label=1 高于 label=0 的判别；tie 取平均秩）。

    返回 [0,1]；0.5 = 无判别力。类别高度不平衡下 AUC 仍稳健（秩检验）。
    """
    n = len(labels)
    pos = [s for l, s in zip(labels, scores) if l > 0]
    neg = [s for l, s in zip(labels, scores) if l == 0]
    if not pos or not neg:
        return 0.5
    ranks = _ranks(list(scores))
    np_ = len(pos)
    nn = len(neg)
    rank_pos = 0.0
    for i, l in enumerate(labels):
        if l > 0:
            rank_pos += ranks[i]
    return (rank_pos - np_ * (np_ + 1) / 2.0) / (np_ * nn)


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    rx = _ranks([float(v) for v in xs])
    ry = _ranks([float(v) for v in ys])
    n = len(rx)
    mx = sum(rx) / n
    my = sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx * vy > 0 else 0.0


def bin_table(scores: list[float], labels: list[int], n_bins: int = 10) -> list[dict]:
    """按分数分位分桶，输出每桶平均命中（appearance rate）+ 相对基率 lift。"""
    n = len(labels)
    if n == 0:
        return []
    base_rate = sum(labels) / n
    order = sorted(range(n), key=lambda i: scores[i])
    buckets = [0] * n_bins
    hit = [0] * n_bins
    per_bin = max(1, n // n_bins)
    for idx, pos in enumerate(order):
        b = min(n_bins - 1, pos // per_bin)
        buckets[b] += 1
        hit[b] += labels[pos]
    out = []
    for b in range(n_bins):
        rate = (hit[b] / buckets[b]) if buckets[b] else 0.0
        out.append({
            "bin": b,
            "n": buckets[b],
            "appearance_rate": round(rate, 4),
            "lift_over_base": round(rate / base_rate, 3) if base_rate else 0.0,
            "score_mean": round(sum(scores[i] for i in range(b * per_bin, min(b * per_bin + per_bin, n))) / max(1, min(per_bin, n - b * per_bin)), 4) if buckets[b] else 0.0,
        })
    return out


def decile_lift(scores: list[float], labels: list[int]) -> dict:
    """top-decile / bottom-decile 命中率 + 相对基率 lift（按分数排序）。"""
    n = len(labels)
    base_rate = sum(labels) / n if n else 0.0
    order = sorted(range(n), key=lambda i: scores[i])
    k = max(1, n // 10)
    top_hits = sum(labels[order[i]] for i in range(n - k, n))
    bot_hits = sum(labels[order[i]] for i in range(k))
    top_rate = top_hits / k
    bot_rate = bot_hits / k
    return {
        "top_decile_hit": round(top_hits, 4),
        "bot_decile_hit": round(bot_hits, 4),
        "top_rate": round(top_rate, 4),
        "bot_rate": round(bot_rate, 4),
        "top_lift": round(top_rate / base_rate, 3) if base_rate else 0.0,
        "bot_lift": round(bot_rate / base_rate, 3) if base_rate else 0.0,
    }


# =========================================================
# 单号特征有效性（LEVEL 1 汇总）
# =========================================================

def single_feature_validity(zone: str, feat_data: dict[str, list[float]],
                            labels: list[int]) -> dict[str, dict]:
    """对单区域（front/back）每个特征输出：auc / spearman / decile-lift / 单调性。"""
    out: dict[str, dict] = {}
    base_rate = sum(labels) / len(labels) if labels else 0.0
    for f in list(feat_data.keys()):
        scores = feat_data[f]
        auc = roc_auc(labels, scores)
        sp = spearman(scores, labels)
        dl = decile_lift(scores, labels)
        # 单调性：比较 top/bottom 桶 appearance rate 的差（>0 表示高分数→高出现）
        mono = dl["top_rate"] - dl["bot_rate"]
        out[f] = {
            "auc": round(auc, 4),
            "spearman": round(sp, 4),
            "top_decile": dl["top_rate"],
            "bottom_decile": dl["bot_rate"],
            "top_lift": dl["top_lift"],
            "bottom_lift": dl["bot_lift"],
            "mono_gap": round(mono, 4),
            "base_rate": round(base_rate, 4),
            "n": len(labels),
        }
    return out


# =========================================================
# Null controls（STEP 14）：deterministic
# =========================================================

def shuffled_feature_aucs(feat_data: dict[str, list[float]], labels: list[int],
                          seeds: int = NULL_SEEDS) -> dict[str, dict]:
    """SHUFFLED_FEATURE：在同一 target 合法号码间打乱 feature 值（保持边际分布），
    记录每次的 AUC 分布；observed AUC 应超过 95 分位才算"超过随机排序波动"。"""
    n = len(labels)
    res: dict[str, dict] = {}
    for f in list(feat_data.keys()):
        scores = feat_data[f]
        obs = roc_auc(labels, scores)
        aucs = []
        for sd in range(seeds):
            rng = random.Random(sd)
            perm = list(range(n))
            rng.shuffle(perm)
            shuffled = [scores[i] for i in perm]
            aucs.append(roc_auc(labels, shuffled))
        aucs.sort()
        p95 = aucs[min(len(aucs) - 1, int(0.95 * len(aucs)))]
        p50 = aucs[len(aucs) // 2]
        res[f] = {
            "observed_auc": round(obs, 4),
            "null_p95": round(p95, 4),
            "null_p50": round(p50, 4),
            "beats_null": bool(obs > p95),
        }
    return res


def random_score_aucs(labels: list[int], seeds: int = NULL_SEEDS) -> dict:
    """RANDOM_SCORE：纯随机分数作为 null discrimination control。"""
    n = len(labels)
    aucs = []
    for sd in range(seeds):
        rng = random.Random(900000 + sd)
        scores = [rng.random() for _ in range(n)]
        aucs.append(roc_auc(labels, scores))
    aucs.sort()
    p95 = aucs[min(len(aucs) - 1, int(0.95 * len(aucs)))]
    p05 = aucs[min(len(aucs) - 1, int(0.05 * len(aucs)))]
    return {"random_auc_p05": round(p05, 4), "random_auc_p50": round(aucs[len(aucs) // 2], 4),
            "random_auc_p95": round(p95, 4)}


# =========================================================
# LEVEL 2：候选组合特征
# =========================================================

def candidate_features(combo: dict[str, list], prev: dict,
                       overlap: dict, structure: dict, sum_span: dict) -> dict:
    """对一个候选组合计算 LEVEL 2 特征（从生产 scorer + 原始统计）。"""
    front = combo.get("front") or []
    back = combo.get("back") or []
    odd = sum(1 for x in front if x % 2 == 1)
    big = sum(1 for x in front if x >= 18)
    pf = set(prev.get("front") or [])
    pb = set(prev.get("back") or [])
    fs = (sum_span or {}).get("front_sum") or {}
    feat = {
        "front_sum": sum(front),
        "front_span": (max(front) - min(front)) if front else 0,
        "back_span": (max(back) - min(back)) if back else 0,
        "odd_cnt": odd,
        "big_cnt": big,
        "front_overlap_prev": len(set(front) & pf),
        "back_overlap_prev": len(set(back) & pb),
        "sum_in_p25_75": int(bool(fs.get("p25") is not None and fs.get("p75") is not None
                                 and fs["p25"] <= sum(front) <= fs["p75"])),
    }
    cs = calculate_combination_score(
        {"front": list(front), "back": list(back)},
        overlap_dist=overlap, structure_stats=structure,
        sum_span_stats=sum_span, prev_front=list(prev.get("front") or []),
        prev_back=list(prev.get("back") or []))
    feat["combo_score"] = cs["score_total"]
    feat["odd_even_match"] = cs["factors"]["odd_even_match"]
    feat["big_small_match"] = cs["factors"]["big_small_match"]
    feat["zone_match"] = cs["factors"]["zone_match"]
    feat["sum_span_match"] = cs["factors"]["sum_span_match"]
    feat["inherit_match"] = cs["factors"]["inherit_match"]
    return feat


def candidate_hit_labels(combo: dict[str, list], target: dict) -> dict:
    fh = len(set(combo.get("front") or []) & set(target.get("front") or []))
    bh = len(set(combo.get("back") or []) & set(target.get("back") or []))
    return {"front_hits": fh, "back_hits": bh, "total_hits": fh + bh}


# =========================================================
# 冗余（STEP 17）：Spearman 相关矩阵（单号特征间）
# =========================================================

def build_feature_inventory() -> dict:
    """STEP 2/3：基于审计的真实生产代码（analyzer/scorer/recommender/final_score）。

    provenance:
      RAW_HISTORY_DERIVED   纯由 issues[:t] 历史统计派生
      CANDIDATE_DERIVED     由候选组合本身计算
      OUTCOME_FEEDBACK      依赖历史开奖命中反馈（P2 证明对 selector 无边际选择作用）
      STATIC_RULE           静态规则/阈值
      RANDOM                纯随机
    不要根据名称猜——每一项都来自真实代码 inventory。
    """
    return {
        "single_features": {
            "freq_ratio": {"name": "frequency", "zone": "front+back", "lookback": "FULL evidence",
                           "formula": "count(num in issues[:t]) / n", "normalization": "0-1 ratio",
                           "direction": "higher=hotter", "interaction": "drives hot/cold/heat",
                           "consumer": "analyzer.analyze -> A/B front_freq + scorer heat(recent_100)",
                           "provenance": "RAW_HISTORY_DERIVED", "note": "D heat = recent_100/100"},
            "recent_ratio": {"name": "recent frequency", "zone": "front+back", "lookback": "recent_window=50",
                             "formula": "count(num in last 50) / 50", "normalization": "0-1",
                             "direction": "higher=recent hot", "interaction": "drives A/B 50% weight + D heat",
                             "consumer": "analyzer.front_recent_freq -> A/B _weighted", "provenance": "RAW_HISTORY_DERIVED"},
            "cur_omit": {"name": "omission (current)", "zone": "front+back", "lookback": "to last hit",
                         "formula": "consecutive missing draws", "normalization": "int",
                         "direction": "higher=cooler", "interaction": "maps to cycle_status",
                         "consumer": "analyzer.front_cur_omit -> B cold + scorer missing", "provenance": "RAW_HISTORY_DERIVED"},
            "avg_omit": {"name": "omission (avg cycle)", "zone": "front+back", "lookback": "FULL",
                         "formula": "mean gap between appearances", "normalization": "draws",
                         "direction": "context for cur_omit", "interaction": "omit_ratio=cur/avg",
                         "consumer": "analyzer.analyze_missing_cycle", "provenance": "RAW_HISTORY_DERIVED"},
            "max_omit": {"name": "omission (max)", "zone": "front+back", "lookback": "FULL",
                         "formula": "max historical gap", "normalization": "int",
                         "direction": "at_max -> strong recall", "interaction": "cycle_status at_max",
                         "consumer": "analyzer.front_max_omit", "provenance": "RAW_HISTORY_DERIVED"},
            "omit_ratio": {"name": "omission ratio", "zone": "front+back", "lookback": "FULL",
                           "formula": "cur_omit / avg_omit", "normalization": ">=0", "direction": "higher=overdue",
                           "interaction": "over_avg/at_max signal", "consumer": "derived", "provenance": "RAW_HISTORY_DERIVED"},
            "trend": {"name": "temperature/trend", "zone": "front+back", "lookback": "30 vs 100",
                      "formula": "recent_30 rate - recent_100 rate", "normalization": "[-1,1] clamped -> 0-100",
                      "direction": "positive=warming", "interaction": "scorer trend 25%",
                      "consumer": "analyzer.analyze_number_temperature -> D", "provenance": "RAW_HISTORY_DERIVED"},
            "hot": {"name": "hot indicator", "zone": "front+back", "lookback": "FULL",
                    "formula": "top-10 by freq", "normalization": "0/1", "direction": "1=hot",
                    "interaction": "A/B hot sample", "consumer": "analyzer.front_hot", "provenance": "RAW_HISTORY_DERIVED"},
            "in_prev": {"name": "previous-draw overlap indicator", "zone": "front+back", "lookback": "1",
                         "formula": "1 if num in issues[t-1]", "normalization": "0/1", "direction": "1=repeat candidate",
                         "interaction": "scorer inherit 15% cap", "consumer": "analyzer + scorer inherit",
                         "provenance": "RAW_HISTORY_DERIVED"},
            "zone": {"name": "size zone", "zone": "front(5)/back(2)", "lookback": "static",
                     "formula": "static zone index by range", "normalization": "int", "direction": "distributional",
                     "interaction": "scorer zone_match", "consumer": "analyzer zone_dist", "provenance": "STATIC_RULE"},
        },
        "candidate_features": {
            "front_sum": {"name": "sum", "zone": "front", "source": "CANDIDATE_DERIVED"},
            "front_span": {"name": "span", "zone": "front", "source": "CANDIDATE_DERIVED"},
            "back_span": {"name": "back span", "zone": "back", "source": "CANDIDATE_DERIVED"},
            "odd_cnt": {"name": "odd/even", "zone": "front", "source": "CANDIDATE_DERIVED"},
            "big_cnt": {"name": "size balance", "zone": "front", "source": "CANDIDATE_DERIVED"},
            "front_overlap_prev": {"name": "overlap(prev)", "zone": "front", "source": "CANDIDATE_DERIVED"},
            "back_overlap_prev": {"name": "overlap(prev)", "zone": "back", "source": "CANDIDATE_DERIVED"},
            "combo_score": {"name": "structure/base score", "zone": "combo", "source": "CANDIDATE_DERIVED"},
            "odd_even_match": {"name": "odd/even match", "zone": "combo", "source": "CANDIDATE_DERIVED"},
            "big_small_match": {"name": "big/small match", "zone": "combo", "source": "CANDIDATE_DERIVED"},
            "zone_match": {"name": "zone match", "zone": "combo", "source": "CANDIDATE_DERIVED"},
            "sum_span_match": {"name": "sum/span match", "zone": "combo", "source": "CANDIDATE_DERIVED"},
            "inherit_match": {"name": "inherit match", "zone": "combo", "source": "CANDIDATE_DERIVED"},
        },
        "final_score_components": {
            "base": {"provenance": "STATIC_RULE", "note": "60 + rank adjust; no history"},
            "history": {"provenance": "OUTCOME_FEEDBACK", "note": "strategy avg hit over history (P2: no marginal selector effect)"},
            "recent": {"provenance": "OUTCOME_FEEDBACK", "note": "recent hit list mean (P2: no marginal selector effect)"},
            "structure": {"provenance": "CANDIDATE_DERIVED", "note": "reuses scorer combo 5 factors"},
            "risk": {"provenance": "STATIC_RULE", "note": "structural penalty (repeat/odd/extreme/sum outlier)"},
        },
        "ablation_variants": {
            "FULL": "D control (production weights)",
            "NO_HEAT": "remove number.heat (frequency)",
            "NO_MISSING": "remove number.missing (omission)",
            "NO_TREND": "remove number.trend (temperature)",
            "NO_INHERIT": "remove number.inherit (single overlap)",
            "NO_INHERIT_MATCH": "remove combo.inherit_match (combo overlap)",
            "NO_ODD_EVEN": "remove combo.odd_even_match (structure)",
            "NO_BIG_SMALL": "remove combo.big_small_match (structure)",
            "NO_ZONE": "remove combo.zone_match (structure)",
            "NO_SUM_SPAN": "remove combo.sum_span_match (sum/span)",
        },
        "weight_handling_rule": (
            "ZERO-then-normalize: set removed feature's production weight key to 0.0, keep all other "
            "weights unchanged; scorer._normalize_weights renormalizes remaining to sum=1 (production "
            "builtin behavior). NO post-hoc weight retuning. Rule frozen in definition BEFORE results."
        ),
    }


def bh_fdr(p_values: list[float], alpha: float = 0.05) -> list[float]:
    """Benjamini-Hochberg FDR 阈值（参考输出，非确认门）。

    返回与输入同顺序的 q-value：落在 BH 阈值以下的保留原 p，以上置 1.0。"""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    thr = [alpha * (r + 1) / m for r in range(m)]
    k = -1
    for r, idx in enumerate(order):
        if p_values[idx] <= thr[r]:
            k = r
    q = [0.0] * m
    for r, idx in enumerate(order):
        q[idx] = min(1.0, p_values[idx]) if r <= k else 1.0
    return [round(x, 5) for x in q]


def redundancy_matrix(feat_data: dict[str, list[float]],
                      corr_features: list[str] | None = None,
                      threshold: float = 0.7) -> dict:
    """单号特征间 |spearman| 相关矩阵；>threshold 者归入 REDUNDANT GROUPS。"""
    feats = [f for f in (corr_features or list(feat_data.keys())) if f in feat_data]
    m = len(feats)
    mat: dict[str, dict[str, float]] = {}
    for i in range(m):
        mat[feats[i]] = {}
        for j in range(m):
            mat[feats[i]][feats[j]] = round(spearman(feat_data[feats[i]], feat_data[feats[j]]), 3)
    # 高相关对（i<j, |rho|>=threshold）
    pairs = []
    for i in range(m):
        for j in range(i + 1, m):
            r = abs(mat[feats[i]][feats[j]])
            if r >= threshold:
                pairs.append({"a": feats[i], "b": feats[j], "abs_spearman": round(r, 3)})
    pairs.sort(key=lambda p: -p["abs_spearman"])
    return {"matrix": mat, "high_corr_pairs": pairs, "threshold": threshold}
