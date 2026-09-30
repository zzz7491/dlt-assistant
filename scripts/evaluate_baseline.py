#!/usr/bin/env python3
"""P2-1 推荐模型评测基线 — 一键运行脚本。

用法：
  python scripts/evaluate_baseline.py
  python scripts/evaluate_baseline.py --warmup 100 --seeds 25 --eval-count 300
  python scripts/evaluate_baseline.py --skip-d   # 跳过 D（快速验证）

输出：
  reports/evaluation/p21-baseline.json
  reports/evaluation/P21-BASELINE-REPORT.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def generate_report(result: dict) -> str:
    """从 walk-forward 结果生成 Markdown 报告。"""
    meta = result["meta"]
    m = result["metrics"]
    rs = result["random_stats"]
    comp = result["comparisons"]
    ps = result["payout_summary"]

    def strat_row(name: str) -> str:
        s = m.get(name)
        if not s:
            return f"| {name} | — | — | — | — | — | — | — | — | — |"
        tc = s["prize_tier_counts"]
        p_hits = s["prize_hit_count"]
        pout = ps.get(name, {})
        known = pout.get("known_fixed_payout_total", 0)
        roi_lb = pout.get("roi_lower_bound_total", "—")
        roi_det = "partial" if not pout.get("roi_fully_determinable", True) else "exact"
        c1 = tc.get("1", 0) + tc.get("2", 0)
        c3 = tc.get("3", 0) + tc.get("4", 0) + tc.get("5", 0)
        c_low = tc.get("6", 0) + tc.get("7", 0) + tc.get("8", 0) + tc.get("9", 0)
        return (f"| {name} | {s['n']} | {s['front_hit_mean']:.3f} | {s['back_hit_mean']:.3f} | "
                f"{s['total_hit_mean']:.3f} | {s['thresholds']['front_ge3']} | "
                f"{s['thresholds']['back_eq2']} | {p_hits} ({c1}+{c3}+{c_low}) | "
                f"{pout.get('cost_total', s['n']*2)} | {known} | {roi_lb} ({roi_det}) |")

    lines = [
        "# P2-1 Recommendation Evaluation Baseline Report",
        "",
        f"Evaluation version: `{meta['evaluation_version']}`",
        f"Data: {meta['earliest_issue']} → {meta['latest_issue']} "
        f"({meta['total_issues']} periods, {meta['warmup']} warmup excluded)",
        f"Evaluated draws: **{meta['evaluated_periods']}**",
        f"Random seeds: {meta['random_seeds']}",
        f"Cost per ticket: {meta['cost_per_ticket']} RMB",
        f"Elapsed: {result['elapsed_sec']}s",
        "",
        "## Strategy Comparison Table",
        "",
        "| Strategy | N | Front Mean | Back Mean | Total Mean | >=3 Front | 2 Back | Prize Hits | Cost | Known Payout | ROI (lower bound) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        strat_row("A"),
        strat_row("B"),
        strat_row("C"),
        strat_row("D"),
        strat_row("SIMPLE_FREQ"),
        strat_row("SELECTOR"),
        "",
        "## Random Baseline Statistics (multi-seed)",
        "",
        f"- Seeds: {rs['seeds']}",
        f"- Total hit mean: {rs['total_hit_mean']}",
        f"- Total hit median: {rs['total_hit_median']}",
        f"- Total hit std: {rs['total_hit_std']}",
        f"- Total hit p05: {rs['total_hit_p05']}",
        f"- Total hit p95: {rs['total_hit_p95']}",
        f"- Front hit mean: {rs['front_hit_mean']}",
        f"- Back hit mean: {rs['back_hit_mean']}",
        "",
        "## Comparison vs Random",
        "",
        "| Strategy | Total Mean | Diff vs Random | In p05-p95 | Within 1σ |",
        "|---|---|---|---|---|",
    ]
    for name in ("A", "B", "C", "D", "SIMPLE_FREQ", "SELECTOR"):
        c = comp.get(name)
        if c:
            lines.append(
                f"| {name} | {c['strategy_total_mean']} | {c['diff_vs_random']:+} | "
                f"{'YES' if c['in_random_p05_p95'] else 'NO'} | "
                f"{'YES' if c['within_1sd'] else 'NO'} |"
            )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "This report is a **historical measurement only**. It does NOT recommend",
        "purchasing any lottery ticket or predict future outcomes.",
        "Lottery draws are independent random events; any strategy",
        "observed to outperform random over a finite sample",
        "does not guarantee future performance.",
        "",
    ])
    # Strategy status
    status = meta.get("strategy_status", {})
    if status:
        lines.append("### Strategy evaluation status")
        lines.append("")
        for k, v in status.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="P2-1 evaluation baseline")
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--seeds", type=int, default=25)
    parser.add_argument("--eval-count", type=int, default=None,
                        help="max periods to evaluate (default: all)")
    parser.add_argument("--skip-d", action="store_true", help="skip D strategy (fast)")
    parser.add_argument("--skip-selector", action="store_true", help="skip selector eval")
    parser.add_argument("--history", default="public/data/dlt_history.json")
    parser.add_argument("--out-dir", default="reports/evaluation")
    args = parser.parse_args()

    from src.evaluation.walk_forward import run_and_report
    result = run_and_report(
        history_path=args.history,
        out_dir=args.out_dir,
        warmup=args.warmup,
        random_seeds=args.seeds,
        eval_count=args.eval_count,
        include_d=not args.skip_d,
        include_selector=not args.skip_selector,
    )

    # 生成 MD 报告
    report_md = generate_report(result)
    out_p = pathlib.Path(args.out_dir) / "P21-BASELINE-REPORT.md"
    out_p.write_text(report_md, encoding="utf-8")
    print(f"[P2-1] Report → {out_p}")
    print(f"[P2-1] Done. Evaluated {result['meta']['evaluated_periods']} draws in "
          f"{result['elapsed_sec']}s.")


if __name__ == "__main__":
    main()
