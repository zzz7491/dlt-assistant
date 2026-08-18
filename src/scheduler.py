"""每日编排入口：抓取 -> 保存 -> 分析 -> 推荐 -> 报告 ->（可选）图表/通知。

用法：
  每日定时（容器内 cron）： python -m src.scheduler
  一次性运行（验证/手动）： python -m src.scheduler --once
  指定配置：               python -m src.scheduler --config config/settings.yaml
"""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

import yaml

from .analyzer import (
    analyze,
    analyze_previous_overlap,
    analyze_number_temperature,
    analyze_missing_cycle,
    analyze_structure_distribution,
    analyze_sum_span,
)
from .database import load
from .recommender import recommend, STRATEGY_LABELS
from .recommendations import build_records, next_issue, save as save_recs
from .reporter import build_report, write_report
from .scraper import run as scrape_run


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(config_path: str = "config/settings.yaml") -> dict:
    cfg = load_config(config_path)
    db_path = cfg["database"]["path"]

    print("开始大乐透分析")

    # 1) 抓取并保存（增量，自动合并去重）
    before = len(load(db_path).get("issues", []))
    db = scrape_run(cfg, db_path)
    added = len(db["issues"]) - before
    print(f"数据更新：新增 {added} 期")
    issues = sorted(db["issues"], key=lambda x: x["issue"])
    recent = issues[-cfg["scrape"]["recent_issues"]:]

    # 2) 分析
    analysis = analyze(recent, cfg)
    print("分析完成")

    # 3) 娱乐推荐（A/B/C 三策略 + D 综合评分型）
    stats = {
        "overlap": analyze_previous_overlap(issues),
        "temperature": analyze_number_temperature(issues),
        "missing_cycle": analyze_missing_cycle(issues),
        "structure": analyze_structure_distribution(issues),
        "sum_span": analyze_sum_span(issues),
        "prev_issue": issues[-1] if issues else None,
    }
    recommendations = recommend(analysis, cfg, stats=stats)

    # 3.1) 落盘推荐记录（供开奖验证模块比对），按策略分别记录
    rec_cfg = cfg["recommend"]
    latest_issue = int(db["issues"][-1]["issue"])
    target_issue = next_issue(latest_issue)
    rec_date = datetime.now().strftime("%Y-%m-%d")
    all_recs: list[dict[str, Any]] = []
    for key in ("A", "B", "C", "D"):
        label = f"{key}-{STRATEGY_LABELS[key]}"
        combos = recommendations.get(key, [])
        if not combos:
            continue
        recs = build_records(combos, target_issue, label, date=rec_date)
        if key == "D":
            c0 = combos[0]
            for r in recs:  # D 策略记录附带模型版本/评分/依据（向后兼容，A/B/C 记录字段不变）
                r["model_version"] = c0.get("model_version")
                r["score_total"] = c0.get("score_total")
                r["basis"] = c0.get("basis")
        all_recs.extend(recs)
    save_recs(rec_cfg["log_path"], all_recs)
    print(f"[scheduler] 已记录推荐 {len(all_recs)} 组（A/B/C/D），目标期号 {target_issue}")

    # 4) 开奖验证（比对历史推荐 vs 真实开奖），在生成报告前取得汇总
    val_cfg = cfg.get("validate", {})
    validation_summary: dict[str, Any] | None = None
    if val_cfg.get("enabled"):
        try:
            from .validator import validate as run_validate
            vr = run_validate(rec_cfg["log_path"], db_path, val_cfg.get("report_path", "reports/validation_report.md"))
            validation_summary = vr.get("summary")
        except Exception as e:
            print(f"[validator] 验证失败（已跳过）：{e}")

    # 4.5) 推荐回测（C-2-Step3：命中统计/策略表现/因素有效性 → backtest_summary.json；失败不阻断）
    if val_cfg.get("enabled", True):
        try:
            from .backtest import run_backtest
            bt = run_backtest(rec_cfg["log_path"], db_path,
                              val_cfg.get("backtest_path", "reports/backtest_summary.json"))
            print(f"[backtest] 回测完成：已验证 {bt['total_periods']} 期")
        except Exception as e:
            print(f"[backtest] 回测失败（已跳过）：{e}")

    # 4.6) 推荐复盘（C-2-Step4：单期复盘/因素三态/策略排行 → reflection_report.json；失败不阻断）
    if val_cfg.get("enabled", True):
        try:
            from .reflection import run_reflect
            bt_path = val_cfg.get("backtest_path", "reports/backtest_summary.json")
            rf = run_reflect(rec_cfg["log_path"], db_path, bt_path,
                             val_cfg.get("reflection_path", "reports/reflection_report.json"))
            print(f"[reflection] 复盘完成：{len(rf['periods'])} 期已复盘")
        except Exception as e:
            print(f"[reflection] 复盘失败（已跳过）：{e}")

    # 5) 生成报告（含验证统计汇总）
    gen_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "generated_at": gen_at,
        "source": db.get("source", ""),
        "range": f"{recent[0]['issue']} ~ {recent[-1]['issue']}",
        "validation": validation_summary,
    }
    report_text = build_report(meta, analysis, recommendations)
    rep_cfg = cfg["report"]
    report_name = datetime.now().strftime(rep_cfg["filename_fmt"])
    report_path = write_report(report_text, f"{rep_cfg['dir']}/{report_name}")
    print("报告生成完成")

    # 6) 可选：图表
    if cfg.get("charts", {}).get("enabled"):
        try:
            from charts.generate import generate_charts
            generate_charts(analysis, recent, cfg)
        except Exception as e:  # 扩展失败不应阻断主流程
            print(f"[charts] 生成失败（已跳过）：{e}")

    # 7) 可选：飞书通知
    feishu_cfg = cfg.get("notify", {}).get("feishu", {})
    if feishu_cfg.get("enabled") and feishu_cfg.get("webhook"):
        try:
            from .notifier.feishu import FeishuNotifier
            notifier = FeishuNotifier(feishu_cfg["webhook"], feishu_cfg.get("secret", ""))
            ok = notifier.send_text(f"大乐透娱乐分析已更新：{report_path}\n（仅供娱乐，不预测中奖）")
            print(f"[feishu] 通知发送：{'成功' if ok else '失败'}")
        except Exception as e:
            print(f"[feishu] 通知失败（已跳过）：{e}")

    summary = {
        "issues_analyzed": len(recent),
        "range": meta["range"],
        "report_path": report_path,
        "strategies": len(recommendations),
    }
    print(f"[scheduler] 完成：分析 {summary['issues_analyzed']} 期，报告 -> {report_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="大乐透AI娱乐分析助手 - 调度入口")
    parser.add_argument("--once", action="store_true", help="立即执行一次（不依赖 cron）")
    parser.add_argument("--config", default="config/settings.yaml", help="配置文件路径")
    args = parser.parse_args()
    try:
        run_once(args.config)
    except Exception as e:  # 顶层兜底：cron 下异常也输出可读错误而非裸 traceback
        print(f"[scheduler] 运行失败：{type(e).__name__}: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
