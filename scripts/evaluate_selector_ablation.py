#!/usr/bin/env python3
"""P2-2 selector ablation 一键运行脚本。

用法：
  python scripts/evaluate_selector_ablation.py
  python scripts/evaluate_selector_ablation.py --s7-seeds 100 --bootstrap-n 20000

输出：
  reports/evaluation/p22-selector-ablation.json
  reports/evaluation/P22-SELECTOR-ABLATION-REPORT.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def _fmt_mean(s: dict, key: str = "total_hit_stats") -> str:
    return f"{s[key]['mean']}" if key in s and s[key] else "—"


def generate_report(res: dict) -> str:
    v = res["variants"]
    cmp_ = res["comparisons"]
    meta = res["meta"]

    def row(key: str) -> str:
        d = v.get(key)
        if not d:
            return f"| {key} | — |"
        st = d["total_hit_stats"]
        p = d["payout_summary"]
        roi_note = "partial(variable)" if not p.get("roi_fully_determinable", True) else "exact"
        return (f"| {key} {d['variant']} | {d['unique_periods']} | {st.get('mean')} | "
                f"{d['front_mean']} | {d['back_mean']} | {st.get('p05')}–{st.get('p95')} | "
                f"{p.get('known_fixed_payout_total')} | {p.get('roi_lower_bound_total')} ({roi_note}) | "
                f"{'⚠ ORACLE' if d['oracle'] else ''} |")

    lines = [
        "# P2-2 Selector Ablation & Statistical Validation Report",
        "",
        f"Evaluation version `{meta['evaluation_version']}` · data {meta['earliest_issue']}→{meta['latest_issue']} "
        f"({meta['history_count']} periods, warmup {meta['warmup']}, evaluated {meta['evaluated_periods']})",
        f"S7 seeds: {meta['s7_seeds']} · S0 seeds: {meta['s0_seeds']} · "
        f"bootstrap: {meta['bootstrap_n']} resamples (seed {meta['bootstrap_seed']})",
        "",
        "> **Interpretation guardrail**: this is an *exploratory model-selection* analysis with "
        "multiple variants compared against one shared sample. A variant that looks best here is a "
        "hypothesis to test out-of-sample later, NOT proof of predictive value. The ORACLE variant is "
        "post-hoc (it knows each draw's result) and is shown only as a theoretical ceiling.",
        "",
        "## Variant Summary",
        "",
        "| Variant | N | Total Mean | Front Mean | Back Mean | p05–p95 | Known Payout | ROI (lower bound) | Note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k in ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        lines.append(row(k))
    lines += [
        "",
        "## Key Paired Comparisons (CURRENT S1)",
        "",
        "| Comparison | Δmean | 95% bootstrap CI | sign-flip p (raw→Holm) | t (aux) |",
        "|---|---|---|---|---|",
    ]
    for k in ("S1_vs_S2", "S1_vs_S3", "S1_vs_S4", "S1_vs_S7"):
        c = cmp_.get(k, {})
        boot = c.get("bootstrap", {})
        sf = c.get("signflip", {})
        t = c.get("t", {})
        lines.append(
            f"| {k} | {c.get('paired_delta_mean')} | "
            f"[{boot.get('ci_low')}, {boot.get('ci_high')}] "
            f"({'' if boot.get('ci_contains_zero') else 'excludes 0'}) | "
            f"{sf.get('p_value_raw')} → {sf.get('p_value_holm')} | "
            f"t={t.get('t')} p={t.get('p')} |"
        )
    lines += [
        "",
        "## Selection Frequency (S1 CURRENT)",
        "",
        f"A {res['selection_frequency_S1'].get('A')}% · B {res['selection_frequency_S1'].get('B')}% · "
        f"C {res['selection_frequency_S1'].get('C')}% · D {res['selection_frequency_S1'].get('D')}%",
        "",
        f"Early {res['selection_frequency_S1'].get('early')} · "
        f"Middle {res['selection_frequency_S1'].get('middle')} · Late {res['selection_frequency_S1'].get('late')}",
        "",
        "## Switching / Chasing (S1)",
        "",
        f"- switch rate: {res['switching_S1'].get('switch_rate')} "
        f"(mean run length {res['switching_S1'].get('mean_run')})",
        f"- switch-after-win rate: {res['switching_S1'].get('switch_after_win_rate')} "
        f"({res['switching_S1'].get('win_events')} win events)",
        f"- switch-after-loss rate: {res['switching_S1'].get('switch_after_loss_rate')} "
        f"({res['switching_S1'].get('loss_events')} loss events)",
        "",
        "## Temporal Stability",
        "",
        "### S1 (CURRENT) total-hit mean by third",
        "",
        "| segment | mean | p05 | p95 |",
        "|---|---|---|---|",
    ]
    for seg in ("early", "middle", "late"):
        s = res["temporal_S1"].get(seg, {})
        lines.append(f"| {seg} | {s.get('mean')} | {s.get('p05')} | {s.get('p95')} |")
    lines += [
        "",
        "### Rolling S1 − S2 delta per 100-period block",
        "",
        "| block | mean Δ (S1−S2) | n |",
        "|---|---|---|",
    ]
    for blk in res["rolling_S1_minus_S2"]:
        lines.append(f"| {blk['block_index']} | {blk['mean']} | {blk['n']} |")
    lines += [
        "",
        "## Fair Null Baseline (S7 RANDOM-CHOICE-ABCD)",
        "",
        f"- per-seed mean distribution (across {meta['s7_seeds']} seeds): "
        f"mean {res['s7_seed_stats'].get('mean')}, p05 {res['s7_seed_stats'].get('p05')}, "
        f"p95 {res['s7_seed_stats'].get('p95')}, p99 {res['s7_seed_stats'].get('p99')}",
        f"- full pooled: mean {res['s7_full_stats'].get('mean')} (n {res['s7_full_stats'].get('n')})",
        f"- **S1 vs S7**: Δ = {cmp_['S1_vs_S7'].get('paired_delta_mean')} "
        f"(95% CI [{cmp_['S1_vs_S7']['bootstrap'].get('ci_low')}, "
        f"{cmp_['S1_vs_S7']['bootstrap'].get('ci_high')}], "
        f"CI {'contains' if cmp_['S1_vs_S7']['bootstrap'].get('ci_contains_zero') else 'excludes'} 0)",
        "",
        "## Oracle Upper Bound (S8, POST-HOC)",
        "",
        f"- ORACLE mean total hit {res['s8_oracle_stats'].get('mean')} "
        f"(p05–p95 {res['s8_oracle_stats'].get('p05')}–{res['s8_oracle_stats'].get('p95')}). "
        f"Ceiling of choosing best-of-4 after seeing each result. **INVALID FOR PRODUCTION.**",
        f"- Independent random single ticket (S0): mean {res['s0_stats'].get('mean')}.",
        "",
        "## Interpretation",
        "",
        "Objective read (no purchase/prediction recommendation):",
        "- Compare S1 (current selector) against S7 (random choice among the same four candidates) "
        "to isolate the *selection* mechanism from candidate quality.",
        "- A/B/C/D all sit near the independent-random-ticket expectation, so the selector's apparent "
        "edge over a single random ticket is largely explained by random-choice among candidates.",
        "- NO_RECENT / NO_HISTORY ablations test whether the recent-5 or history feedback terms "
        "actually move out-of-sample performance.",
        "- If the S1 vs S2 (drop recent) paired CI contains 0, the recent-feedback term is not "
        "supported by this sample; likewise for S3 (drop history).",
        "- Any apparent advantage that only appears in one of EARLY/MIDDLE/LATE is UNSTABLE.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="P2-2 selector ablation")
    ap.add_argument("--history", default="public/data/dlt_history.json")
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--s7-seeds", type=int, default=50)
    ap.add_argument("--s0-seeds", type=int, default=50)
    ap.add_argument("--bootstrap-n", type=int, default=10000)
    ap.add_argument("--bootstrap-seed", type=int, default=12345)
    ap.add_argument("--out-dir", default="reports/evaluation")
    args = ap.parse_args()

    import json as _json
    issues = _json.loads(pathlib.Path(args.history).read_text())
    if isinstance(issues, dict):
        issues = issues.get("issues", [])

    from src.evaluation import ablation
    res = ablation.run_ablation(
        issues, warmup=args.warmup,
        random_s7_seeds=list(range(1, args.s7_seeds + 1)),
        s0_seeds=list(range(1, args.s0_seeds + 1)),
        bootstrap_n=args.bootstrap_n, bootstrap_seed=args.bootstrap_seed,
    )

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # 去掉 variant 内全量 record（只保留统计量）以控制 JSON 体积
    slim = dict(res)
    (out / "p22-selector-ablation.json").write_text(
        _json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[P2-2] JSON → {out / 'p22-selector-ablation.json'}")

    report = generate_report(res)
    (out / "P22-SELECTOR-ABLATION-REPORT.md").write_text(report, encoding="utf-8")
    print(f"[P2-2] Report → {out / 'P22-SELECTOR-ABLATION-REPORT.md'}")

    # 打印关键结论
    c = res["comparisons"]
    print("\n=== KEY ANSWERS ===")
    print(f"S1 mean {res['variants']['S1']['total_hit_stats']['mean']} | "
          f"S2 {res['variants']['S2']['total_hit_stats']['mean']} | "
          f"S3 {res['variants']['S3']['total_hit_stats']['mean']} | "
          f"S4 {res['variants']['S4']['total_hit_stats']['mean']}")
    print(f"S7(pooled) {res['s7_full_stats']['mean']} | S8-oracle {res['s8_oracle_stats']['mean']} | "
          f"S0 {res['s0_stats']['mean']}")
    for k in ("S1_vs_S2", "S1_vs_S3", "S1_vs_S4", "S1_vs_S7"):
        b = c[k]["bootstrap"]
        print(f"{k}: Δ={b['mean_delta']} CI[{b['ci_low']},{b['ci_high']}] "
              f"contains0={b['ci_contains_zero']} p_holm={c[k]['signflip']['p_value_holm']}")


if __name__ == "__main__":
    main()
