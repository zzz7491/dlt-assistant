#!/usr/bin/env python3
"""P3-2 窗口敏感性评测 runner（research only；不改生产 window/策略/26112）。

流程（防过拟合顺序）：
  1. 验证 frozen dataset SHA256 = ba4bfb09…（否则 STOP）
  2. 冻结 p32-window-definition.json（定义早于结果）
  3. 并行计算 common-target × window 候选矩阵（A/B/C/D 真实生产函数；equivalence 校验）
  4. 每 strategy × window 指标 + 随机 50-seed 基线
  5. within-strategy window 比较（vs 1000 control）：paired bootstrap + sign-flip + Holm
  6. dev（前 80%）形成窗口候选 → 冻结 selection_before_holdout.json → final holdout（后 20%）一次确认
  7. temporal / rolling / regime 稳定性 + FULL vs 1000
  8. per-strategy decision（KEEP_1000 / SUPPORTED_SHORTER_WINDOW / SUPPORTED_FULL / NO_WINDOW_EDGE）
  9. production-cap finding + 报告

禁止：修改 production cap/recommender/策略/selector/final_score/26112/frontend；push；deploy。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import window_study as ws
from src.evaluation import statistics as stats
from src.evaluation import prize

DATASET_SHA_EXPECTED = "ba4bfb09d46aa66ab72c2ba3f72057e37ffca293ac76e1e3a21dde77f1e4dbbf"


def verify_dataset(path: str) -> tuple[bool, int]:
    from src.evaluation import history_integrity as hi
    d = json.loads(pathlib.Path(path).read_text())
    recs = d.get("issues", d)
    h = hi.dataset_sha256(recs)
    return (h == DATASET_SHA_EXPECTED, len(recs))


def hash_obj(o: dict) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def write_definition(out_dir: pathlib.Path, target_count: int) -> dict:
    defn = {
        "dataset_sha256": DATASET_SHA_EXPECTED,
        "windows": ws.WINDOWS,
        "common_warmup": ws.COMMON_WARMUP,
        "target_count": target_count,
        "strategies": ["A", "B", "C", "D"],
        "random_seeds": ws.RANDOM_SEEDS,
        "metrics": ["front_mean", "back_mean", "total_mean",
                    "front_ge3", "front_ge4", "back_ge1", "back_eq2", "prize_hits",
                    "known_payout", "cost", "roi_status"],
        "bootstrap_seed": ws.BOOTSTRAP_SEED,
        "bootstrap_resamples": ws.BOOTSTRAP_N,
        "multiple_comparison_method": "holm-bonferroni",
        "dev_ratio": ws.DEV_RATIO,
        "note": "frozen BEFORE results; do NOT modify windows/rules after run",
        "frozen_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    defn["definition_sha256"] = hash_obj(defn)
    (out_dir / "p32-window-definition.json").write_text(json.dumps(defn, indent=2, ensure_ascii=False),
                                                         encoding="utf-8")
    print(f"[P3-2] definition frozen (sha {defn['definition_sha256'][:16]})")
    return defn


def equivalence_check(t_idxs, windows, cfg, n=20) -> dict:
    """STEP 7：optimized (parallel compute_candidates) vs direct production recommend() 抽样一致。"""
    from src.analyzer import analyze
    from src.recommender import recommend
    mismatches = []
    sample = t_idxs[:n] if len(t_idxs) >= n else t_idxs
    for t in sample:
        for w in windows:
            ev = ws.evidence_for(t, w)
            an = analyze(ev, cfg)
            direct = {}
            abc = recommend(an, cfg, stats=None)
            for k in ("A", "B", "C"):
                if k in abc:
                    direct[k] = {"front": list(abc[k][0]["front"]), "back": list(abc[k][0]["back"])}
            st = ws._stats(ev, ws._ISSUES[t - 1])
            d = recommend(an, cfg, stats=st)
            if "D" in d:
                direct["D"] = {"front": list(d["D"][0]["front"]), "back": list(d["D"][0]["back"])}
            opt = ws.compute_candidates(t, w, cfg)
            for k in ("A", "B", "C", "D"):
                if k in direct:
                    if direct[k]["front"] != opt.get(k, {}).get("front") or direct[k]["back"] != opt.get(k, {}).get("back"):
                        mismatches.append((t, w, k))
    return {"checked": len(sample) * len(windows), "mismatches": mismatches,
            "equivalence_pass": not mismatches}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/research/dlt-full-history.json")
    ap.add_argument("--out-dir", default="reports/evaluation")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--no-parallel", action="store_true")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 验证 dataset hash（STOP if mismatch）
    ok, count = verify_dataset(str(root / args.dataset))
    if not ok:
        print("[P3-2] ⚠ DATASET SHA MISMATCH — STOP (P3-2 STOP)")
        return
    print(f"[P3-2] dataset verified sha=ba4bfb09… count={count}")

    issues = ws.load_issues(str(root / args.dataset))
    cfg = ws.production_cfg()

    # 2) 冻结 definition
    common_warmup = ws.COMMON_WARMUP
    t_idxs = list(range(common_warmup, len(issues)))  # 后 1930 targets
    write_definition(out_dir, len(t_idxs))

    # 3) equivalence（抽样）
    eq = equivalence_check(t_idxs, ws.WINDOWS, cfg, n=10)
    print(f"[P3-2] equivalence: {eq['equivalence_pass']} (checked {eq['checked']}, mismatches {len(eq['mismatches'])})")
    if not eq["equivalence_pass"]:
        print("[P3-2] ⚠ equivalence FAIL — 不允许用优化路径，本 Gate 失败")
        return

    # 4) 候选矩阵
    if args.no_parallel:
        # shell-level 并行 worker 已生成的 chunk files（multiprocessing 被沙箱阻止）
        chunks_dir = root / ".agnes" / "work" / "p32"
        matrix: dict[tuple, dict] = {}
        total_cells = 0
        for c in range(10):
            cf = chunks_dir / f"matrix_chunk_{c}.json"
            if not cf.exists():
                print(f"[P3-2] ⚠ missing {cf.name}"); return
            raw = json.loads(cf.read_text())
            for t_str, rec in raw.items():
                t_int = int(t_str)
                for w in ws.WINDOWS:
                    matrix[(t_int, w)] = rec[w]
                    total_cells += 1
        print(f"[P3-2] matrix loaded from 10 chunk files: {total_cells} cells")
    else:
        print(f"[P3-2] building candidate matrix: {len(t_idxs)} targets × {len(ws.WINDOWS)} windows "
              f"(strategies A/B/C/D, parallel={args.workers}) ...")
        matrix = ws.run_matrix(t_idxs, ws.WINDOWS, workers=args.workers)
        print(f"[P3-2] matrix built ({len(matrix)} cells)")

    # 5) 每 strategy × window 指标
    metrics = {}
    for strat in ("A", "B", "D"):
        for w in ws.WINDOWS:
            fh = bh = 0
            tot = 0
            ge3 = ge4 = back1 = back2 = prize_hits = 0
            payout = 0.0
            n_rec = 0
            for t in t_idxs:
                c = matrix.get((t, w), {}).get(strat)
                if c is None:
                    continue
                hfh, hbh, htot = ws.hits_of(c, ws._ISSUES[t])
                fh += hfh; bh += hbh; tot += htot
                ge3 += (hfh >= 3); ge4 += (hfh >= 4)
                back1 += (hbh >= 1); back2 += (hbh == 2)
                pb = prize.payout_breakdown(hfh, hbh)
                prize_hits += (pb["tier"] is not None)
                payout += pb["known_fixed_payout"]
                n_rec += 1
            n = n_rec or 1
            # ROI 仅按已知固定奖计算（一/二等浮动不计金额）→ lower_bound_only
            roi_lb = round((payout - 2.0 * n_rec) / (2.0 * n_rec), 4) if n_rec else 0.0
            metrics[f"{strat}_{w}"] = {
                "strategy": strat, "window": w, "n": n_rec,
                "front_mean": round(fh / n, 4), "back_mean": round(bh / n, 4),
                "total_mean": round(tot / n, 4),
                "front_ge3": ge3, "front_ge4": ge4, "back_ge1": back1, "back_eq2": back2,
                "prize_hits": prize_hits, "known_payout": round(payout, 2),
                "cost": 2.0 * n_rec,
                "roi_lower_bound": roi_lb,
                "roi_status": "lower_bound_only",
            }

    # 随机基线（invariant，同 1930 targets，50 seeds）
    from src.evaluation import baselines
    random_per_seed = []
    for seed in range(1, ws.RANDOM_SEEDS + 1):
        hits = []
        for t in t_idxs:
            combo = baselines.random_combo(seed * 1000000 + t)
            hits.append(ws.hits_of(combo, ws._ISSUES[t])[2])
        random_per_seed.append(sum(hits) / len(hits))
    random_stats = stats.summary_stats(random_per_seed)

    # 6) within-strategy window 比较（vs 1000 control）
    t0 = t_idxs
    def tot_vec(w, s):
        return [ws.hits_of(matrix.get((t, w), {}).get(s, {"front": [], "back": []}), ws._ISSUES[t])[2]
                if s in matrix.get((t, w), {}) else 0.0 for t in t0]
    control = {s: tot_vec("1000", s) for s in ("A", "B", "D")}
    window_vecs = {s: {w: tot_vec(w, s) for w in ("50", "100", "300", "500", "FULL")} for s in ("A", "B", "D")}

    comparisons = {}
    for s in ("A", "B", "D"):
        ps = []
        for w in ("50", "100", "300", "500", "FULL"):
            a = window_vecs[s][w]
            b = control[s]
            boot = stats.paired_bootstrap_ci(a, b, n_resamples=ws.BOOTSTRAP_N, seed=ws.BOOTSTRAP_SEED)
            sf = stats.paired_sign_flip_pvalue(a, b, one_sided=True)
            comparisons[f"{s}_{w}_vs_1000"] = {
                "delta": boot["mean_delta"], "ci": [boot["ci_low"], boot["ci_high"]],
                "contains0": boot["ci_contains_zero"], "p_raw": sf["p_value"],
            }
            ps.append(sf["p_value"])
        adj = stats.holm_adjust(ps)
        for i, w in enumerate(("50", "100", "300", "500", "FULL")):
            comparisons[f"{s}_{w}_vs_1000"]["p_holm"] = adj[i]

    # 7) dev / final-holdout split（80/20 on the 1930 targets）
    dev_count = int(len(t_idxs) * ws.DEV_RATIO)
    dev_t = t_idxs[:dev_count]
    hold_t = t_idxs[dev_count:]

    def pick_best_dev_window(s):
        """dev-only：选 dev 上 total_mean 最高的窗口（记录，冻结）。"""
        best_w, best_m = None, -1.0
        for w in ("50", "100", "300", "500", "1000", "FULL"):
            vec = [ws.hits_of(matrix.get((t, w), {}).get(s, {"front": [], "back": []}), ws._ISSUES[t])[2]
                   if s in matrix.get((t, w), {}) else 0.0 for t in dev_t]
            m = sum(vec) / len(vec)
            if m > best_m:
                best_m, best_w = m, w
        return best_w, best_m

    selection = {}
    for s in ("A", "B", "D"):
        best_w, best_m = pick_best_dev_window(s)
        selection[s] = {"dev_best_window": best_w, "dev_best_mean": round(best_m, 4),
                        "dev_control_1000_mean": round(sum(control[s][:len(dev_t)]) / len(dev_t), 4)}
    (out_dir / "p32-window-selection-before-holdout.json").write_text(
        json.dumps(selection, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[P3-2] dev-selected windows frozen: " +
          ", ".join(f"{s}={selection[s]['dev_best_window']}" for s in selection))

    # final holdout 一次确认（dev-selected window vs 1000）
    holdout_confirm = {}
    for s in ("A", "B", "D"):
        w = selection[s]["dev_best_window"]
        a = [ws.hits_of(matrix.get((t, w), {}).get(s, {"front": [], "back": []}), ws._ISSUES[t])[2]
             if s in matrix.get((t, w), {}) else 0.0 for t in hold_t]
        b = [ws.hits_of(matrix.get((t, "1000"), {}).get(s, {"front": [], "back": []}), ws._ISSUES[t])[2]
             if s in matrix.get((t, "1000"), {}) else 0.0 for t in hold_t]
        boot = stats.paired_bootstrap_ci(a, b, n_resamples=ws.BOOTSTRAP_N, seed=ws.BOOTSTRAP_SEED + 7)
        sf = stats.paired_sign_flip_pvalue(a, b, one_sided=True)
        holdout_confirm[s] = {
            "window": w, "holdout_mean": round(sum(a) / len(a), 4),
            "holdout_1000_mean": round(sum(b) / len(b), 4),
            "delta": boot["mean_delta"], "ci": [boot["ci_low"], boot["ci_high"]],
            "p_raw": sf["p_value"], "confirmed": (not boot["ci_contains_zero"]) and sf["p_value"] < 0.05,
        }

    # 8) FULL vs 1000（关键比较，含 temporal stability）
    full_vs_1000 = {}
    for s in ("A", "B", "D"):
        a = window_vecs[s]["FULL"]
        b = control[s]
        boot = stats.paired_bootstrap_ci(a, b, n_resamples=ws.BOOTSTRAP_N, seed=ws.BOOTSTRAP_SEED)
        sf = stats.paired_sign_flip_pvalue(a, b, one_sided=True)
        seg = stats.temporal_split(a)
        seg1000 = stats.temporal_split(b)
        full_vs_1000[s] = {
            "delta": boot["mean_delta"], "ci": [boot["ci_low"], boot["ci_high"]],
            "contains0": boot["ci_contains_zero"], "p_raw": sf["p_value"],
            "full_temporal": {k: seg[k]["mean"] for k in ("early", "middle", "late")},
            "full_vs_1000_temporal_delta": {k: round(seg[k]["mean"] - seg1000[k]["mean"], 4)
                                             for k in ("early", "middle", "late")},
        }
    full_vs_1000_holm = stats.holm_adjust([full_vs_1000[s]["p_raw"] for s in ("A", "B", "D")])

    # regime split（描述性）
    regime_bounds = {"early": (0, 645), "mid": (645, 1290), "late": (1290, len(t_idxs))}
    regime = {}
    for s in ("A", "B", "D"):
        for w in ("1000", "FULL"):
            vec = [ws.hits_of(matrix.get((t, w), {}).get(s, {"front": [], "back": []}), ws._ISSUES[t])[2]
                   if s in matrix.get((t, w), {}) else 0.0 for t in t_idxs]
            regime[f"{s}_{w}"] = {
                name: round(sum(vec[lo:hi]) / max(1, hi - lo), 4)
                for name, (lo, hi) in regime_bounds.items()
            }

    # 9) per-strategy decision
    def decide(s):
        """per-strategy 窗口决策（基于 holdout 一次确认 + FULL-vs-1000）。"""
        h = holdout_confirm[s]
        f1000 = full_vs_1000[s]
        if h["confirmed"]:
            return "SUPPORTED_FULL" if h["window"] == "FULL" else "SUPPORTED_SHORTER_WINDOW"
        # FULL 显著优于 1000（delta>0 且 CI 排除 0）→ 支持扩展
        if (not f1000["contains0"]) and f1000["delta"] > 0:
            return "SUPPORTED_FULL"
        # 短窗口在 holdout 已确认 已在上面处理；否则：
        #   1000 未被任何更优窗口取代 → 维持 1000；
        #   若 1000 与 FULL 无差异（contains0）且无确认 → 该策略"无窗口 edge"（窗口长度不影响 OOS）
        if f1000["contains0"]:
            return "NO_WINDOW_EDGE"
        return "KEEP_1000"

    decisions = {s: decide(s) for s in ("A", "B", "D")}

    # production-cap finding
    cap_justified = _cap_finding(full_vs_1000, holdout_confirm)

    payload = {
        "meta": {
            "dataset_sha256": DATASET_SHA_EXPECTED,
            "equivalence_pass": eq["equivalence_pass"],
            "common_eval_draws": len(t_idxs),
            "development_draws": len(dev_t),
            "final_holdout_draws": len(hold_t),
            "random_seeds": ws.RANDOM_SEEDS,
            "bootstrap_n": ws.BOOTSTRAP_N, "bootstrap_seed": ws.BOOTSTRAP_SEED,
        },
        "metrics": metrics,
        "random_baseline": random_stats,
        "window_comparisons": comparisons,
        "dev_selection": selection,
        "holdout_confirmation": holdout_confirm,
        "full_vs_1000": full_vs_1000,
        "full_vs_1000_holm": full_vs_1000_holm,
        "regime": regime,
        "decisions": decisions,
        "production_cap_justified": cap_justified,
    }
    (out_dir / "p32-window-results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                                      encoding="utf-8")

    report = _report(payload, selection)
    (out_dir / "P32-WINDOW-STUDY-REPORT.md").write_text(report, encoding="utf-8")
    print("[P3-2] JSON + report written")
    for s in ("A", "B", "D"):
        print(f"  {s}: decisions={decisions[s]} | full_vs_1000 Δ={full_vs_1000[s]['delta']} "
              f"CI{full_vs_1000[s]['ci']} p={full_vs_1000[s]['p_raw']}")
    print(f"  production 1000 cap justified: {cap_justified}")


def _cap_finding(full_vs_1000, holdout_confirm) -> str:
    """production 1000 cap 是否 justified（storage retention 与 analysis window 是两件事）。

    - 若某策略在 holdout 上明确受益于 FULL（>1000）→ "NO"（1000 太短，需扩展）
    - 若某策略在 holdout 上确认了更短窗口 → "NO"（1000 太长）
    - 否则 → "INSUFFICIENT"（无可靠证据表明 1000 优于 300/500 或劣于 FULL；
      通常 FULL 不更优 → 扩展 retention 到全历史无 OOS 收益，但"恰好 1000"也未被精确证成）
    """
    if any((not f["contains0"]) and f["delta"] > 0 for f in full_vs_1000.values()):
        return "NO"
    if any(h["confirmed"] and h["window"] != "FULL" for h in holdout_confirm.values()):
        return "NO"
    return "INSUFFICIENT"


def _report(p: dict, selection: dict) -> str:
    m = p["metrics"]; rb = p["random_baseline"]; comp = p["window_comparisons"]
    f1000 = p["full_vs_1000"]; reg = p["regime"]; dec = p["decisions"]
    lines = [
        "# P3-2 Window Sensitivity & Strict OOS Study",
        "",
        f"dataset sha256 `{DATASET_SHA_EXPECTED[:16]}` · common OOS {p['meta']['common_eval_draws']} draws "
        f"(dev {p['meta']['development_draws']} / final holdout {p['meta']['final_holdout_draws']}) · "
        f"equivalence {p['meta']['equivalence_pass']}",
        "",
        "> Window semantics: target t 之前 issues[:t]；rolling W 取最后 W；FULL 为 expanding（t 之前全部）。"
        "target/未来绝不进入窗口。FULL 在历史不足 1000 期时 = rolling 1000（min(n,W)）。"
        "所有 A/B/C/D 调用真实生产 recommend()；C 为不变随机对照。",
        "",
        "## Random Baseline (invariant, 50 seeds)",
        "",
        f"mean {rb.get('mean')} · median {rb.get('median')} · std {rb.get('std')} · "
        f"p05 {rb.get('p05')} · p95 {rb.get('p95')} · p99 {rb.get('p99')}",
        "",
        "## Strategy × Window (mean total hits, common 1930 OOS)",
        "",
        "| strategy | 50 | 100 | 300 | 500 | 1000 | FULL |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in ("A", "B", "D"):
        row = [s]
        for w in ws.WINDOWS:
            row.append(str(m[f"{s}_{w}"]["total_mean"]))
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## FULL vs 1000 (key comparison)", ""]
    for s in ("A", "B", "D"):
        f = f1000[s]
        lines.append(f"- {s}: Δ={f['delta']} CI[{f['ci'][0]},{f['ci'][1]}] "
                     f"({'contains 0' if f['contains0'] else 'excludes 0'}) p={f['p_raw']}; "
                     f"temporal Δ early/mid/late={f['full_vs_1000_temporal_delta']['early']}/"
                     f"{f['full_vs_1000_temporal_delta']['middle']}/{f['full_vs_1000_temporal_delta']['late']}")
    lines += ["", "## Development Selection (frozen before holdout)", ""]
    for s in ("A", "B", "D"):
        lines.append(f"- {s}: dev-best window = {selection[s]['dev_best_window']} "
                     f"(mean {selection[s]['dev_best_mean']} vs 1000 {selection[s]['dev_control_1000_mean']})")
    lines += ["", "## Final Holdout Confirmation", ""]
    for s, h in p["holdout_confirmation"].items():
        lines.append(f"- {s}: window {h['window']} → holdout {h['holdout_mean']} vs 1000 {h['holdout_1000_mean']} "
                     f"(Δ {h['delta']}, p {h['p_raw']}) → CONFIRMED={h['confirmed']}")
    lines += ["", "## Per-Strategy Decision", ""]
    for s in ("A", "B", "D"):
        lines.append(f"- **{s}: {dec[s]}**")
    lines += ["", "## Production 1000 Cap Finding", "",
              f"**{p['production_cap_justified']}**", "",
              "(storage retention 与 strategy analysis window 是不同架构问题；"
              "本 Gate 不改 production cap)", "",
              "## Limitations", "",
              "- cross-source verification = NO（P3-1 单一源）；结论基于 500 单一源 full history。",
              "- D 的 temperature 子窗口（近30/近100）为硬编码 clamp，改外层窗口对它们影响有限（effective window 语义已在 report 记录）。",
              "- 窗口比较为 exploratory；任一 SUPPORTED 结论仍需在 P3-3/P2-4 前做更强 OOS 确认。",
              "",
              "## Production Integrity", "",
              "- production cap / recommender / strategies / selector / final_score / 26112 / frontend: UNCHANGED",
              "- this gate: research only",
              ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
