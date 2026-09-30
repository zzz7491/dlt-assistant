"""P3-4 SELECTOR EDGE DECOMPOSITION & ROBUSTNESS（research only；不改生产 selector/权重/候选/C seed/26112）。

科学目标（唯一）：解释 CURRENT selector 早期研究（P2-2 S1 vs S7 Δ=0.051, Holm p=0.102）
的表观优势为何在 P2-3/P3-2 final holdout 未确认，并将 edge 分解到具体机制：
  1) selector 本身稳定选择能力？
  2) 对某个 candidate（尤其 C）的结构性偏好？
  3) candidate set 整体收益？
  4) candidate 间高度相关的假象？
  5) 特定历史时期/regime？
  6) seed / candidate-generation 偶然性？
  7) sample noise / multiple testing？

重建契约（STEP 4）：
  - CURRENT selector = 真实生产 compute_final_scores（生产权重 + walk-forward OOS maps
    + structure_ctx=None + prev_draw）→ is_primary。与 P2-2 _apply_selector / P2-3 pick_T0
    算法一致（同 cache 0 mismatch 已验证）。
  - A/B/C/D 候选复用 P3-2 matrix cache（window=1000, seed=20260930）；不重新生成已冻结候选。
  - OOS maps（history/recent/rank）在 P3-4 population（1930 common OOS, warmup=1000）上
    walk-forward 重建，从 target 1 起累积（协议写入 definition；P2 已证 feedback 无
    边际选择作用，故与 P2-2 warmup=100 的差异如实记录而非掩盖）。
"""
from __future__ import annotations

import random
from typing import Any

from ..final_score import DEFAULT_WEIGHTS, compute_final_scores
from ..analyzer import analyze
from ..recommender import recommend
from . import baselines

STRATS = ("A", "B", "C", "D")
PROD_WEIGHTS = dict(DEFAULT_WEIGHTS)  # base .40 history .20 recent .15 structure .20 risk .05


# =========================================================
# STEP 4：重建 CURRENT selector（walk-forward OOS + 生产 compute_final_scores）
# =========================================================

def reconstruct_selector(issues: list[dict], cand: dict[int, dict[str, dict]],
                         t_idxs: list[int],
                         c_combos: dict[int, dict] | None = None,
                         c_hits: dict[int, dict[str, int]] | None = None) -> list[dict[str, Any]]:
    """逐期重建 CURRENT selector。

    返回 per-target record：
      {t, sel, sel_hits, cand_hits{g:th}, margin, tie,
       components{base,history,recent,structure,risk}, final_scores{g}, effective_sample, stage}
    c_combos/c_hits 可覆盖 P3-2 cache 的 C（seed 实验用）；A/B/D 恒来自 cand。
    """
    oos_acc = {g: [] for g in STRATS}
    out: list[dict] = []
    for ti in t_idxs:
        prev = issues[ti - 1]
        target = issues[ti]
        ch = {}
        for g in STRATS:
            if g == "C" and c_combos and c_hits and ti in c_combos:
                comb = c_combos[ti]
            else:
                comb = cand[ti][g]
            ch[g] = len(set(comb["front"]) & set(target["front"])) + len(set(comb["back"]) & set(target["back"]))
        # walk-forward OOS maps（用前 t-1…累积到 target 1）
        eff = max((len(v) for v in oos_acc.values()), default=0)
        hist = {g: (sum(oos_acc[g]) / len(oos_acc[g]) if oos_acc[g] else 0.0) for g in STRATS}
        recent = {g: list(oos_acc[g][-5:]) for g in STRATS}
        ranked = sorted(oos_acc, key=lambda g: -(sum(oos_acc[g]) / len(oos_acc[g]) if oos_acc[g] else -1))
        rank = {g: (i + 1) for i, g in enumerate(ranked)}
        recs = [{"strategy": g, "front": (c_combos[ti] if c_combos and c_hits and ti in c_combos and g == "C"
                                            else cand[ti][g])["front"],
                 "back": (c_combos[ti] if c_combos and c_hits and ti in c_combos and g == "C"
                           else cand[ti][g])["back"]} for g in STRATS]
        scored = compute_final_scores(
            recs, effective_sample=eff, strategy_rank=rank, history_map=hist, recent_map=recent,
            structure_ctx=None, prev_draw={"front": prev["front"], "back": prev["back"]},
            weights=PROD_WEIGHTS)
        prim = next((s for s in scored if s.get("is_primary")), None)
        sel = str(prim["strategy"]).split("-")[0] if prim else "NONE"
        with_score = sorted((s for s in scored if isinstance(s.get("final_score"), (int, float))),
                            key=lambda s: -s["final_score"])
        margin = (with_score[0]["final_score"] - with_score[1]["final_score"]) if len(with_score) >= 2 else 100.0
        tie = margin == 0.0
        comps = {}
        finals = {}
        for s in scored:
            gk = str(s.get("strategy", "")).split("-")[0]
            finals[gk] = s.get("final_score")
            bd = s.get("final_breakdown") or {}
            if gk == sel:
                comps = {
                    "base": bd.get("base"), "history": bd.get("history"), "recent": bd.get("recent"),
                    "structure": bd.get("structure"), "risk": bd.get("risk"),
                    "stage": bd.get("stage"), "effective_sample": bd.get("effective_sample"),
                }
        out.append({
            "t": ti, "sel": sel, "sel_hits": ch[sel] if sel in ch else 0,
            "cand_hits": ch, "margin": margin, "tie": tie,
            "components": comps, "final_scores": finals,
            "random_exp": sum(ch.values()) / len(ch),
        })
        for g in STRATS:
            oos_acc[g].append(ch[g])
    return out


# =========================================================
# STEP 5：candidate set decomposition
# =========================================================

def candidate_decomposition(recs: list[dict]) -> dict:
    per_t = {
        "best": [], "worst": [], "mean4": [], "median4": [], "var4": [],
        "cur_minus_mean": [], "cur_minus_random_exp": [], "regret_vs_oracle": [],
    }
    import statistics as _st
    for r in recs:
        h = [r["cand_hits"][g] for g in STRATS]
        per_t["best"].append(max(h))
        per_t["worst"].append(min(h))
        per_t["mean4"].append(sum(h) / 4.0)
        per_t["median4"].append(_st.median(h))
        m = sum(h) / 4.0
        per_t["var4"].append(sum((x - m) ** 2 for x in h) / 4.0)
        per_t["cur_minus_mean"].append(r["sel_hits"] - m)
        per_t["cur_minus_random_exp"].append(r["sel_hits"] - r["random_exp"])
        per_t["regret_vs_oracle"].append(max(h) - r["sel_hits"])  # oracle = post-hoc ceiling
    n = len(recs)
    return {k: round(sum(v) / n, 4) for k, v in per_t.items()}


# =========================================================
# STEP 6/7：selection-conditional + counterfactual matrix
# =========================================================

def selection_conditional(recs: list[dict]) -> dict:
    out = {}
    n = len(recs)
    for g in STRATS:
        sel_idx = [i for i, r in enumerate(recs) if r["sel"] == g]
        uncond_mean = sum(r["cand_hits"][g] for r in recs) / n
        cond_mean = (sum(recs[i]["cand_hits"][g] for i in sel_idx) / len(sel_idx)) if sel_idx else 0.0
        out[g] = {
            "selection_count": len(sel_idx),
            "selection_share": round(100.0 * len(sel_idx) / n, 3),
            "mean_hits_when_selected": round(cond_mean, 4),
            "unconditional_mean_hits": round(uncond_mean, 4),
            "conditional_uplift": round(cond_mean - uncond_mean, 4),
        }
    return out


def counterfactual_matrix(recs: list[dict]) -> dict[str, dict[str, float]]:
    """row = CURRENT selected strategy；column = 该期实际采用 X 的平均 total hits。

    若 C 选中期里其他 candidate 同样高 → selector 识别的是"易命中时期"而非 C。
    """
    mat: dict[str, dict[str, float]] = {}
    for row_g in STRATS:
        rows = [r for r in recs if r["sel"] == row_g]
        if not rows:
            mat[row_g] = {col: 0.0 for col in STRATS}
            continue
        mat[row_g] = {col: round(sum(r["cand_hits"][col] for r in rows) / len(rows), 4) for col in STRATS}
    return mat


# =========================================================
# STEP 8：pairwise candidate differences
# =========================================================

def pairwise_differences(recs: list[dict]) -> dict[str, dict[str, Any]]:
    import itertools
    out = {}
    for a, b in itertools.combinations(STRATS, 2):
        diffs = [r["cand_hits"][a] - r["cand_hits"][b] for r in recs]
        wins = sum(1 for d in diffs if d > 0)
        losses = sum(1 for d in diffs if d < 0)
        ties = sum(1 for d in diffs if d == 0)
        out[f"{a}_minus_{b}"] = {
            "mean": round(sum(diffs) / len(diffs), 4),
            "median": round(sorted(diffs)[len(diffs) // 2], 4),
            "win": wins, "loss": losses, "tie": ties,
        }
    return out


# =========================================================
# STEP 9：margin analysis
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


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx * vy > 0 else 0.0


def margin_analysis(recs: list[dict], scope: str = "full", dev_count: int | None = None) -> dict:
    sel_recs = recs[:dev_count] if scope == "dev" else (recs[dev_count:] if scope == "holdout" else recs)
    margins = [r["margin"] for r in sel_recs]
    adv = [r["sel_hits"] - r["random_exp"] for r in sel_recs]
    sp = spearman(margins, adv)
    # 冻结 buckets：Q1..Q4 + top10%（full population margin 分位，dev 冻结后应用）
    q_edges = _quartiles([r["margin"] for r in recs]) if dev_count is None else _quartiles(margins)
    buckets = {"Q1": [], "Q2": [], "Q3": [], "Q4": [], "top10": []}
    top10_cut = _pct([r["margin"] for r in recs], 90.0)
    for r in sel_recs:
        m = r["margin"]
        for bi in range(4):
            lo = q_edges[bi]
            hi = q_edges[bi + 1] if bi < 3 else float("inf")
            if lo <= m < hi:
                buckets[f"Q{bi+1}"].append(r)
                break
        if m >= top10_cut:
            buckets["top10"].append(r)
    bstat = {}
    for b, rs in buckets.items():
        if not rs:
            bstat[b] = {"n": 0, "adv_mean": 0.0, "cur_mean": 0.0}
            continue
        bstat[b] = {
            "n": len(rs),
            "adv_mean": round(sum(r["sel_hits"] - r["random_exp"] for r in rs) / len(rs), 4),
            "cur_mean": round(sum(r["sel_hits"] for r in rs) / len(rs), 4),
        }
    finite = [r["margin"] for r in recs]
    _q = _quartiles(finite)[:4]  # 4 finite cut points
    return {"spearman_margin_advantage": round(sp, 4), "buckets": bstat,
            "quartile_edges": [round(x, 2) for x in _q], "top10_cut": round(top10_cut, 2)}


def _quartiles(vals: list[float]) -> list[float]:
    s = sorted(vals)
    n = len(s)
    return [s[int(n * p / 100.0)] for p in (0, 25, 50, 75)] + [float("inf")]


def _pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# =========================================================
# STEP 10：component decomposition（P3-3 已证 history/recent 无独立预测证据）
# =========================================================

def component_decomposition(recs: list[dict]) -> dict:
    """component value 与 selected-candidate 相对优势的关系（仅描述 ranking 机制，
    不重新包装 history/recent 为有效特征）。"""
    out = {}
    for comp in ("base", "history", "recent", "structure", "risk"):
        vals = [r["components"].get(comp) for r in recs if r["components"].get(comp) is not None]
        adv = [r["sel_hits"] - r["random_exp"] for r in recs if r["components"].get(comp) is not None]
        out[comp] = {
            "mean": round(sum(vals) / len(vals), 4) if vals else None,
            "std": round((sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / len(vals)) ** 0.5, 4) if len(vals) > 1 else 0.0,
            "spearman_vs_advantage": round(spearman(vals, adv), 4) if len(vals) >= 3 else None,
            "n": len(vals),
        }
    return out


# =========================================================
# STEP 11：candidate correlation（hits + number overlap）
# =========================================================

def candidate_correlation(recs: list[dict], cand: dict[int, dict[str, dict]]) -> dict:
    import itertools
    import math
    series = {g: [r["cand_hits"][g] for r in recs] for g in STRATS}
    n = len(recs)
    corr = {}
    for a, b in itertools.combinations(STRATS, 2):
        x, y = series[a], series[b]
        mx, my = sum(x) / n, sum(y) / n
        cov = sum((u - mx) * (v - my) for u, v in zip(x, y)) / n
        vx = math.sqrt(sum((u - mx) ** 2 for u in x) / n)
        vy = math.sqrt(sum((v - my) ** 2 for v in y) / n)
        corr[f"{a}_{b}"] = {"pearson": round(cov / (vx * vy), 4) if vx * vy > 0 else 0.0,
                            "spearman": round(spearman(x, y), 4)}
    # number overlap（front/back Jaccard，per-draw 平均）
    jf = []
    jb = []
    exact = 0
    sample = recs[:min(500, n)]  # descriptive 上限 500 足够稳定
    for r in sample:
        for a, b in itertools.combinations(STRATS, 2):
            fa, fb = set(cand[r["t"]][a]["front"]), set(cand[r["t"]][b]["front"])
            ba, bb = set(cand[r["t"]][a]["back"]), set(cand[r["t"]][b]["back"])
            jf.append(len(fa & fb) / len(fa | fb) if fa | fb else 0.0)
            jb.append(len(ba & bb) / len(ba | bb) if ba | bb else 0.0)
            if fa == fb and ba == bb:
                exact += 1
    return {
        "hits_correlation": corr,
        "front_jaccard_mean": round(sum(jf) / len(jf), 4) if jf else 0.0,
        "back_jaccard_mean": round(sum(jb) / len(jb), 4) if jb else 0.0,
        "exact_pair_overlap_rate": round(exact / (len(sample) * 6), 4) if sample else 0.0,
        "note": "high pairwise correlation -> small candidate-spread -> fair-null variance small; small deltas look large",
    }


# =========================================================
# STEP 12/13：temporal robustness（rolling + quintile + leave-era-out）
# =========================================================

def rolling_window(recs: list[dict], sizes=(100, 200, 300)) -> dict:
    deltas = [r["sel_hits"] - r["random_exp"] for r in recs]
    out = {}
    for w in sizes:
        blocks = []
        for i in range(0, len(deltas) - w + 1, w):
            chunk = deltas[i:i + w]
            blocks.append({"start": i, "n": len(chunk), "mean": round(sum(chunk) / len(chunk), 4)})
        out[f"rolling_{w}"] = blocks
    return out


def quintile_eras(recs: list[dict]) -> dict:
    deltas = [r["sel_hits"] - r["random_exp"] for r in recs]
    n = len(recs)
    seg = n // 5
    out = {}
    for qi in range(5):
        lo = qi * seg
        hi = n if qi == 4 else (qi + 1) * seg
        chunk = deltas[lo:hi]
        cur = [recs[i]["sel_hits"] for i in range(lo, hi)]
        rnd = [recs[i]["random_exp"] for i in range(lo, hi)]
        out[f"Q{qi+1}"] = {
            "range": [recs[lo]["t"], recs[hi - 1]["t"]],
            "current_mean": round(sum(cur) / len(cur), 4),
            "fair_random_mean": round(sum(rnd) / len(rnd), 4),
            "delta": round(sum(chunk) / len(chunk), 4),
            "n": len(chunk),
        }
    return out


def leave_era_out(recs: list[dict]) -> dict:
    """5 连续 fold，leave-one-era-out（描述性 robustness；不重训 selector）。"""
    deltas = [r["sel_hits"] - r["random_exp"] for r in recs]
    n = len(recs)
    seg = n // 5
    full_delta = sum(deltas) / n
    out = {"full_delta": round(full_delta, 4)}
    for qi in range(5):
        keep = [d for i, d in enumerate(deltas) if not (qi * seg <= i < min(n, (qi + 1) * seg or n))]
        out[f"drop_era{qi+1}"] = {
            "n": len(keep),
            "delta": round(sum(keep) / len(keep), 4) if keep else None,
            "direction_same_as_full": (sign(keep) == sign(deltas)) if keep else None,
        }
    return out


def sign(vals: list[float]) -> str:
    m = sum(vals) / len(vals) if vals else 0.0
    return "pos" if m > 0.0005 else ("neg" if m < -0.0005 else "zero")


# =========================================================
# STEP 14/15：nulls（frequency-matched + conditional stratified）
# =========================================================

def _permutation_mean(sel_labels: list[str], cand_hits_matrix: list[dict[str, int]]) -> float:
    return sum(cand_hits_matrix[i][sel_labels[i]] for i in range(len(sel_labels))) / len(sel_labels)


def frequency_matched_null(recs: list[dict], n_perm: int = 1000, seed: int = 12345) -> dict:
    """保持 CURRENT 的 A/B/C/D selection frequency，随机打乱选择到各期。

    主 null：回答 CURRENT 是否超过"只是这样选择频率分布"本身。
    """
    labels = [r["sel"] for r in recs]
    mat = [r["cand_hits"] for r in recs]
    observed = _permutation_mean(labels, mat)
    rng = random.Random(seed)
    null_means = []
    for _ in range(n_perm):
        perm = labels[:]
        rng.shuffle(perm)
        null_means.append(_permutation_mean(perm, mat))
    p = sum(1 for m in null_means if m >= observed) / (n_perm + 1)
    return {"observed_mean": round(observed, 4), "null_mean": round(sum(null_means) / len(null_means), 4),
            "null_p05": round(_pct(null_means, 5), 4), "null_p95": round(_pct(null_means, 95), 4),
            "delta": round(observed - sum(null_means) / len(null_means), 4),
            "p_one_sided": round(p, 5), "n_perm": n_perm, "seed": seed}


def conditional_strata(recs: list[dict], dev_recs: list[dict]) -> list[int]:
    """冻结 strata：用 DEV 的 margin 分位（Q1..Q4）给全 population 每期分层。

    不得根据结果调整 strata。"""
    dev_margins = [r["margin"] for r in dev_recs]
    edges = _quartiles(dev_margins)[:4]  # Q1..Q4 边界（不含 inf）
    strata = []
    for r in recs:
        m = r["margin"]
        for qi in range(3):
            if m < edges[qi]:
                strata.append(qi)
                break
        else:
            strata.append(3)
    return strata


def conditional_permutation_null(recs: list[dict], strata: list[int], n_perm: int = 1000,
                                 seed: int = 20260931) -> dict:
    """score-stratum permutation：保持 selection frequency + score-difficulty structure
    （在冻结 margin 层内 permute labels）。"""
    labels = [r["sel"] for r in recs]
    mat = [r["cand_hits"] for r in recs]
    observed = _permutation_mean(labels, mat)
    by_stratum: dict[int, list[int]] = {}
    for i, s in enumerate(strata):
        by_stratum.setdefault(s, []).append(i)
    rng = random.Random(seed)
    null_means = []
    for _ in range(n_perm):
        perm = labels[:]
        for idxs in by_stratum.values():
            lab = [labels[i] for i in idxs]
            rng.shuffle(lab)
            for j, i in enumerate(idxs):
                perm[i] = lab[j]
        null_means.append(_permutation_mean(perm, mat))
    p = sum(1 for m in null_means if m >= observed) / (n_perm + 1)
    return {"observed_mean": round(observed, 4), "null_mean": round(sum(null_means) / len(null_means), 4),
            "delta": round(observed - sum(null_means) / len(null_means), 4),
            "p_one_sided": round(p, 5), "n_perm": n_perm, "seed": seed}


# =========================================================
# STEP 16/17：C seed sensitivity + seed × era
# =========================================================

def c_seed_combo(seed: int, pos: int) -> dict:
    """P2-3 C_SEEDS 语义：random_combo(seed*1000000 + index)；pos = 在 t_idxs 内 0-based 位置。"""
    return baselines.random_combo(seed * 1000000 + pos)


def seed_sensitivity(issues: list[dict], cand: dict[int, dict[str, dict]], t_idxs: list[int],
                     seeds: list[int], production_proxy_seed: int = 0,
                     precomputed: dict[int, dict] | None = None) -> dict:
    """每个 seed：C 候选 = c_seed_combo(seed, pos)；A/B/D 固定（P3-2 cache）。

    重建 walk-forward selector（OOS maps 随 C 变化）→ 记录：
      fixed-C hit mean / CURRENT selector mean / selection shares / seed rank。
    禁止挑 seed；production proxy = seed 0。"""
    results: dict[int, dict] = {}
    for seed in seeds:
        if precomputed and seed in precomputed:
            r = precomputed[seed]
        else:
            c_combos = {}
            for pos, ti in enumerate(t_idxs):
                c_combos[ti] = c_seed_combo(seed, pos)
            r = {"fixed_C_mean": None, "current_mean": None, "shares": None}
            recs = reconstruct_selector(issues, cand, t_idxs, c_combos=c_combos,
                                         c_hits=None)
            fixed = [len(set(c_combos[ti]["front"]) & set(issues[ti]["front"])) +
                     len(set(c_combos[ti]["back"]) & set(issues[ti]["back"])) for ti in t_idxs]
            r["fixed_C_mean"] = round(sum(fixed) / len(fixed), 4)
            r["current_mean"] = round(sum(x["sel_hits"] for x in recs) / len(recs), 4)
            r["shares"] = {g: round(100.0 * sum(1 for x in recs if x["sel"] == g) / len(recs), 2) for g in STRATS}
        results[seed] = r
    # seed rank by fixed_C_mean（stable tie-break by seed）
    order = sorted(seeds, key=lambda s: (-results[s]["fixed_C_mean"], s))
    rank = {s: i + 1 for i, s in enumerate(order)}
    means = [results[s]["fixed_C_mean"] for s in seeds]
    pxy = _pct(means, 5), _pct(means, 95)
    prod_mean = results.get(production_proxy_seed, {}).get("fixed_C_mean")
    if prod_mean is None and production_proxy_seed not in results:
        # proxy seed 未在本次 seeds 中：单独定位其固定 C 表现（不挑 seed）
        c_combos = {ti: c_seed_combo(production_proxy_seed, pos) for pos, ti in enumerate(t_idxs)}
        fixed = [len(set(c_combos[ti]["front"]) & set(issues[ti]["front"])) +
                 len(set(c_combos[ti]["back"]) & set(issues[ti]["back"])) for ti in t_idxs]
        prod_mean = round(sum(fixed) / len(fixed), 4) if fixed else None
    below = 0
    if prod_mean is not None:
        below = sum(1 for m in means if m is not None and m < prod_mean)
    return {
        "n_seeds": len(seeds),
        "production_proxy_seed": production_proxy_seed,
        "production_proxy_fixed_C_mean": prod_mean,
        "production_proxy_percentile": round(100.0 * below / len(means), 2),
        "seed_mean_range": [round(_pct(means, 0), 4), round(_pct(means, 100), 4)],
        "seed_p05": pxy[0], "seed_p95": pxy[1],
        "seed_rank_by_fixed_C_mean": rank,
        "all_seed_fixed_C_means": {str(s): results[s]["fixed_C_mean"] for s in seeds},
        "all_seed_current_means": {str(s): results[s]["current_mean"] for s in seeds},
        "all_seed_shares": {str(s): results[s]["shares"] for s in seeds},
    }


def seed_era_matrix(issues: list[dict], cand: dict[int, dict[str, dict]], t_idxs: list[int],
                    seeds: list[int], n_eras: int = 5) -> dict:
    """seed × era fixed-C 表现矩阵 + rank stability（Spearman rank corr between consecutive eras）。"""
    seg = len(t_idxs) // n_eras
    era_bounds = [(i * seg, len(t_idxs) if i == n_eras - 1 else (i + 1) * seg) for i in range(n_eras)]
    era_means: dict[int, list[float]] = {s: [] for s in seeds}
    base = t_idxs[0]
    for seed in seeds:
        for lo, hi in era_bounds:
            hx = []
            for ti in t_idxs[lo:hi]:
                c = c_seed_combo(seed, ti - base)  # 0-based position in t_idxs（与 seed_sensitivity 一致）
                hx.append(len(set(c["front"]) & set(issues[ti]["front"])) +
                           len(set(c["back"]) & set(issues[ti]["back"])))
            era_means[seed].append(round(sum(hx) / len(hx), 4))
    # rank per era
    rank_per_era: dict[int, dict[int, int]] = {}
    for e in range(n_eras):
        order = sorted(seeds, key=lambda s: (-era_means[s][e], s))
        rank_per_era[e] = {s: i + 1 for i, s in enumerate(order)}
    rho = {}
    for e in range(n_eras - 1):
        s1 = [rank_per_era[e][s] for s in seeds]
        s2 = [rank_per_era[e + 1][s] for s in seeds]
        rho[f"era{e+1}_era{e+2}"] = round(spearman(s1, s2), 4)
    avg_rho = sum(abs(r) for r in rho.values()) / len(rho) if rho else 0.0
    return {
        "era_bounds": [[t_idxs[lo], t_idxs[hi - 1]] for lo, hi in era_bounds],
        "era_means": {str(s): era_means[s] for s in seeds},
        "rank_correlation_consecutive_eras": rho,
        "mean_abs_rank_rho": round(avg_rho, 4),
        "seed_rank_stable": avg_rho >= 0.7,
        "note": "C SEED PERFORMANCE IS UNSTABLE if mean|rho| < 0.7 across eras",
    }


# =========================================================
# STEP 18/19：confirmatory tests H1-H4（FINAL HOLDOUT + Holm）
# =========================================================

def _scoped(recs: list[dict], lo: int, hi: int) -> list[dict]:
    return recs[lo:hi]


def confirmatory_hypotheses(recs: list[dict], dev_count: int,
                            n_perm: int = 1000, bootstrap_n: int = 10000,
                            bootstrap_seed: int = 20260930,
                            strata: list[int] | None = None) -> dict:
    """H1-H4 on FINAL HOLDOUT（dev 只用于机制发现；全 1930 仅描述性）。

    H1: CURRENT > frequency-matched null（holdout）
    H2: CURRENT > conditional stratified null（holdout）
    H3: margin 正校准 relative advantage（holdout, Spearman > 0, permutation p）
    H4: edge 方向稳定 across temporal eras（5 eras, >=4/5 positive delta）
    全部 effect size + CI + raw p + Holm adjusted p。
    """
    from . import statistics as st_
    hold = recs[dev_count:]
    n_hold = len(hold)

    # --- H1 frequency-matched null on holdout ---
    labels = [r["sel"] for r in hold]
    mat = [r["cand_hits"] for r in hold]
    observed_h = _permutation_mean(labels, mat)
    cur_h = [r["sel_hits"] for r in hold]
    rng = random.Random(bootstrap_seed + 1)
    h1_null = []
    for _ in range(n_perm):
        perm = labels[:]
        rng.shuffle(perm)
        h1_null.append(_permutation_mean(perm, mat))
    h1_p = sum(1 for m in h1_null if m >= observed_h) / (n_perm + 1)
    rand_exp_h = [r["random_exp"] for r in hold]
    h1_boot = st_.paired_bootstrap_ci(cur_h, rand_exp_h, n_resamples=bootstrap_n, seed=bootstrap_seed)

    # --- H2 conditional null on holdout（strata 冻结自 dev）---
    if strata is not None:
        hold_strata = strata[dev_count:]
        obs2 = _permutation_mean(labels, mat)
        by_s: dict[int, list[int]] = {}
        for i, s in enumerate(hold_strata):
            by_s.setdefault(s, []).append(i)
        rng2 = random.Random(bootstrap_seed + 2)
        h2_null = []
        for _ in range(n_perm):
            perm = labels[:]
            for idxs in by_s.values():
                lab = [labels[i] for i in idxs]
                rng2.shuffle(lab)
                for j, i in enumerate(idxs):
                    perm[i] = lab[j]
            h2_null.append(_permutation_mean(perm, mat))
        h2_p = sum(1 for m in h2_null if m >= obs2) / (n_perm + 1)
        h2_delta = round(obs2 - sum(h2_null) / len(h2_null), 4)
    else:
        h2_p, h2_delta = 1.0, 0.0

    # --- H3 margin calibration on holdout（permutation p of Spearman）---
    margins_h = [r["margin"] for r in hold]
    adv_h = [r["sel_hits"] - r["random_exp"] for r in hold]
    rho_h = spearman(margins_h, adv_h)
    rng3 = random.Random(bootstrap_seed + 3)
    h3_null = []
    for _ in range(n_perm):
        perm = adv_h[:]
        rng3.shuffle(perm)
        h3_null.append(abs(spearman(margins_h, perm)))
    h3_p = sum(1 for r in h3_null if r >= abs(rho_h)) / (n_perm + 1)

    # --- H4 era stability（5 eras on FULL descriptive; >=4/5 positive）---
    q = quintile_eras(recs)
    deltas = [q[f"Q{i}"]["delta"] for i in range(1, 6)]
    pos_eras = sum(1 for d in deltas if d > 0.0)
    import math
    h4_p = 0.0
    # binomial P(X <= pos_eras) under H0 p=0.5, n=5，检验"全部正向偏多"用 pos 侧：
    # 若 pos_eras >= 4：p = P(X >= pos_eras)（上尾）
    if pos_eras >= 4:
        h4_p = sum(math.comb(5, k) for k in range(pos_eras, 6)) / 32.0
    elif pos_eras <= 1:
        h4_p = sum(math.comb(5, k) for k in range(0, pos_eras + 1)) / 32.0
    else:
        h4_p = 1.0
    h4_p = min(1.0, h4_p)

    # Holm on H1..H4
    ps = [h1_p, h2_p, h3_p, h4_p]
    adj = st_.holm_adjust(ps)
    return {
        "H1_current_vs_freq_matched_null": {
            "holdout_current_mean": round(sum(cur_h) / n_hold, 4),
            "freq_matched_null_mean": round(sum(h1_null) / len(h1_null), 4),
            "fair_random_holdout_mean": round(sum(rand_exp_h) / n_hold, 4),
            "effect_size_delta": round(observed_h - sum(h1_null) / len(h1_null), 4),
            "ci_vs_fair_random": [h1_boot["ci_low"], h1_boot["ci_high"]],
            "p_raw": round(h1_p, 5), "p_holm": round(adj[0], 5),
        },
        "H2_current_vs_conditional_null": {
            "effect_size_delta": h2_delta, "p_raw": round(h2_p, 5), "p_holm": round(adj[1], 5),
        },
        "H3_margin_calibration": {
            "spearman_holdout": round(rho_h, 4), "p_raw": round(h3_p, 5), "p_holm": round(adj[2], 5),
        },
        "H4_era_stability": {
            "era_deltas": deltas, "positive_eras": pos_eras,
            "p_raw": round(h4_p, 5), "p_holm": round(adj[3], 5),
        },
        "holm_order": [round(x, 5) for x in adj],
    }


# =========================================================
# 机制标签（STEP 20）
# =========================================================

def mechanism_labels(conf: dict, seed_res: dict, seed_era: dict,
                     cand_corr: dict, era_deltas: list[float],
                     counterfactual: dict) -> dict:
    labels: list[str] = []
    h1 = conf["H1_current_vs_freq_matched_null"]
    h2 = conf["H2_current_vs_conditional_null"]
    h3 = conf["H3_margin_calibration"]
    h4 = conf["H4_era_stability"]
    holdout_ok = (h1["p_holm"] < 0.05) and (h2["p_holm"] < 0.05)
    seed_robust = seed_res.get("production_proxy_percentile") is not None and \
        seed_era.get("seed_rank_stable", False)
    era_stable = h4["positive_eras"] >= 4
    temporal_ok = era_stable
    if holdout_ok and seed_robust and temporal_ok:
        labels.append("ROBUST_SELECTOR_EDGE")
    # candidate-mix / frequency effects
    cf = counterfactual
    # 若 C 选中期中其他 candidate 平均也高 → selector 识别易命中时期而非 C
    if "C" in cf and cf["C"]:
        cross = [cf["C"][g] for g in STRATS]
        if max(cross) - cf["C"]["C"] < 0.05:
            labels.append("SELECTION_FREQUENCY_EFFECT")
    # candidate correlation high → 假象
    max_p = max((v["pearson"] for v in cand_corr.get("hits_correlation", {}).values()), default=0.0)
    if max_p >= 0.85:
        labels.append("CANDIDATE_MIX_EFFECT")
    # seed
    if not seed_era.get("seed_rank_stable", True):
        labels.append("SEED_DEPENDENT")
    # margin not calibrated
    if h3["spearman_holdout"] is not None and abs(h3["spearman_holdout"]) < 0.05:
        labels.append("UNCALIBRATED_SELECTOR")
    # era dependent
    if 0 < h4["positive_eras"] < 4:
        labels.append("ERA_DEPENDENT")
    # noise compatible
    noise_ok = (h1["p_holm"] >= 0.05) or (h1["effect_size_delta"] is not None and abs(h1["effect_size_delta"]) < 0.02)
    if noise_ok:
        labels.append("NOISE_COMPATIBLE")
    if not labels:
        labels.append("INCONCLUSIVE")
    return {
        "labels": labels,
        "robust_selector_edge": "ROBUST_SELECTOR_EDGE" in labels,
        "noise_compatible": "NOISE_COMPATIBLE" in labels,
        "ml_reconsideration_warranted": "ROBUST_SELECTOR_EDGE" in labels,
        "holdout_confirmed": holdout_ok,
        "seed_robust": seed_robust,
        "temporal_robust": temporal_ok,
        "era_deltas": era_deltas,
    }
