"""P2-2 selector ablation 统计工具（纯函数，stdlib 实现，固定 seed 可复现）。

提供：
  - paired_bootstrap_ci: 配对 bootstrap 置信区间（固定 seed，>=10000 resamples）
  - paired_sign_flip_pvalue: 配对符号翻转（one-sided）p-value
  - paired_wilcoxon_ish / t-stat: 简化 t 统计量 + 正态近似 p（辅助）
  - holm_adjust: Holm-Bonferroni 多重比较校正
  - temporal_split: early/middle/late 三段 + rolling blocks
  - summary_stats: mean/median/std/p05/p95/p99

只描述历史差异，不构成任何推荐或预测。
"""
from __future__ import annotations

import math
import random
import statistics as _stat
from typing import Any, Sequence


def _sorted(vals: Sequence[float]) -> list[float]:
    return sorted(vals)


def _pct(sorted_vals: list[float], p: float) -> float:
    """线性插值百分位（0-100）。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def summary_stats(values: Sequence[float]) -> dict[str, Any]:
    """mean/median/std/p05/p95/p99。"""
    vals = [float(v) for v in values]
    if not vals:
        return {"n": 0}
    s = _sorted(vals)
    return {
        "n": len(vals),
        "mean": round(_stat.fmean(vals), 4),
        "median": round(_stat.median(vals), 4),
        "std": round(_stat.pstdev(vals), 4) if len(vals) >= 2 else 0.0,
        "p05": round(_pct(s, 5), 4),
        "p50": round(_pct(s, 50), 4),
        "p95": round(_pct(s, 95), 4),
        "p99": round(_pct(s, 99), 4),
    }


def paired_deltas(a: Sequence[float], b: Sequence[float]) -> list[float]:
    """同长度配对差值 a_i - b_i。长度不等即报错（保护配对一致性）。"""
    if len(a) != len(b):
        raise ValueError(f"paired arrays differ in length: {len(a)} vs {len(b)}")
    return [float(x) - float(y) for x, y in zip(a, b)]


def paired_bootstrap_ci(a: Sequence[float], b: Sequence[float],
                        n_resamples: int = 10000, seed: int = 12345,
                        ci: float = 95.0) -> dict[str, Any]:
    """配对 bootstrap：对配对差值 resample，估计均值 delta 的置信区间。

    固定 seed → 可复现。返回 {mean_delta, se, ci_low, ci_high, ci_level,
    ci_contains_zero}。
    """
    deltas = paired_deltas(a, b)
    n = len(deltas)
    if n == 0:
        return {"mean_delta": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0,
                "ci_level": ci, "ci_contains_zero": True}
    rng = random.Random(seed)
    mean_delta = _stat.fmean(deltas)
    # bootstrap 均值分布
    boot_means = []
    base = mean_delta
    for _ in range(n_resamples):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        boot_means.append(_stat.fmean(sample))
    boot_means.sort()
    alpha = (100.0 - ci) / 2.0
    ci_low = _pct(boot_means, alpha)
    ci_high = _pct(boot_means, 100.0 - alpha)
    se = _stat.pstdev(boot_means) if len(boot_means) >= 2 else 0.0
    return {
        "mean_delta": round(base, 5),
        "se": round(se, 5),
        "ci_low": round(ci_low, 5),
        "ci_high": round(ci_high, 5),
        "ci_level": ci,
        "ci_contains_zero": (ci_low <= 0.0 <= ci_high),
        "n_resamples": n_resamples,
        "n_pairs": n,
    }


def paired_sign_flip_pvalue(a: Sequence[float], b: Sequence[float],
                            one_sided: bool = True) -> dict[str, Any]:
    """配对符号翻转（permutation）检验：H0 = 差值均值 = 0。

    以非零差值的符号翻转构造 null 分布，比较观测 |delta| 是否极端。
    one_sided=True → 检验 mean_delta > 0（a 优于 b）的单侧 p。
    """
    deltas = paired_deltas(a, b)
    nz = [d for d in deltas if d != 0.0]
    if not nz:
        return {"observed_delta": 0.0, "p_value": 1.0, "n_nonzero": 0,
                "direction": "no_difference"}
    observed = _stat.fmean(deltas)
    rng = random.Random(987654)
    # 构造 null：对非零差值随机翻转符号
    signs = []
    for _ in range(2000):
        fl = [nz[i] * (1 if rng.random() < 0.5 else -1) for i in range(len(nz))]
        signs.append(_stat.fmean(fl))
    # 单侧（检验 delta>0）：null 中 >= observed 的比例
    if observed >= 0:
        extreme = sum(1 for s in signs if s >= observed)
    else:
        extreme = sum(1 for s in signs if s <= observed)
    p = (extreme + 1) / (len(signs) + 1)  # 加一避免 0
    if not one_sided:
        p = min(1.0, 2.0 * p)
    return {
        "observed_delta": round(observed, 5),
        "p_value": round(p, 5),
        "n_nonzero": len(nz),
        "n_resamples": 2000,
        "direction": "positive" if observed > 0 else ("negative" if observed < 0 else "zero"),
    }


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni 校正：返回与输入同顺序的 adjusted p-values。"""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    adj = [0.0] * m
    running_max = 0.0
    for rank, idx in enumerate(order):
        # Holm: p_adj(k) = max_{j<=k} min(1, (m-j+1)*p_(j))，单调不减
        adj_val = min(1.0, (m - rank) * p_values[idx])
        running_max = max(running_max, adj_val)
        adj[idx] = running_max
    return [round(x, 5) for x in adj]


def temporal_split(values: Sequence[float], k: int = 3) -> dict[str, Any]:
    """按时间顺序等分 k 段（默认 early/middle/late），输出每段均值统计。"""
    vals = [float(v) for v in values]
    n = len(vals)
    seg = n // k
    out: dict[str, Any] = {}
    labels = ["early", "middle", "late"] if k == 3 else [f"seg{i}" for i in range(k)]
    for i in range(k):
        start = i * seg
        end = start + seg if i < k - 1 else n
        chunk = vals[start:end]
        out[labels[i]] = summary_stats(chunk)
    return out


def rolling_blocks(values: Sequence[float], block: int = 100) -> list[dict[str, Any]]:
    """按 block 期一块滚动输出每块均值（时间顺序）。"""
    vals = [float(v) for v in values]
    out = []
    for i in range(0, len(vals), block):
        chunk = vals[i:i + block]
        out.append({
            "block_index": i // block,
            "start_idx": i,
            "end_idx": i + len(chunk) - 1,
            "n": len(chunk),
            "mean": round(_stat.fmean(chunk), 4) if chunk else 0.0,
        })
    return out


def t_statistic_paired(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    """配对 t 统计量 + 双侧正态近似 p（辅助展示，非主检验）。"""
    deltas = [float(x) - float(y) for x, y in zip(a, b)]
    n = len(deltas)
    if n < 2:
        return {"t": 0.0, "p": 1.0, "n": n}
    mean = _stat.fmean(deltas)
    se = _stat.pstdev(deltas) / math.sqrt(n)
    t = mean / se if se > 0 else 0.0
    # 双侧正态近似
    p = 2.0 * (1.0 - _norm_cdf(abs(t)))
    return {"t": round(t, 4), "p": round(p, 5), "n": n}


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
