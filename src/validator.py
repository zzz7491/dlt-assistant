"""开奖验证模块：比对历史娱乐推荐号码 vs 真实开奖号码。

仅统计「号码重合个数」（前区命中 / 后区命中 / 总命中），用于娱乐效果回顾，
绝不计算中奖、不预测中奖。

读取：reports/recommendations.json（推荐记录） + data/dlt_history.json（真实开奖）
输出：reports/validation_report.md + 汇总统计（累计生成次数 / 平均命中）
"""
from __future__ import annotations

import os
from typing import Any

from .database import load as load_db
from .recommendations import load as load_recs


def _build_report(results: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    parts = ["# 大乐透娱乐推荐验证报告\n"]
    parts.append(
        f"> 累计生成推荐：**{summary['total']}** 组 ｜ "
        f"已开奖可验证：**{summary['validated']}** 组 ｜ "
        f"平均命中：**{summary['avg_hit']:.2f}** 个\n"
    )
    parts.append("\n## ⚠️ 免责声明\n")
    parts.append(
        "本验证仅统计娱乐推荐与真实开奖的**号码重合个数**，"
        "**不代表任何中奖预测或中奖概率**。彩票开奖为独立随机事件。\n"
    )

    if not results:
        parts.append("\n暂无已开奖的推荐记录可供验证（目标期号尚未开出）。\n")
        return "\n".join(parts)

    parts.append("\n## 逐期验证\n")
    parts.append(
        "| 目标期号 | 策略 | 推荐前区 | 推荐后区 | 开奖前区 | 开奖后区 "
        "| 前区命中 | 后区命中 | 总命中 |"
    )
    parts.append("| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |")
    for r in results:
        fr = " ".join(f"{x:02d}" for x in r["front"])
        br = " ".join(f"{x:02d}" for x in r["back"])
        rf = " ".join(f"{x:02d}" for x in r["real_front"])
        rb = " ".join(f"{x:02d}" for x in r["real_back"])
        parts.append(
            f"| {r['target_issue']} | {r['strategy']} | {fr} | {br} | {rf} | {rb} "
            f"| {r['hit_front']} | {r['hit_back']} | {r['hit_total']} |"
        )
    parts.append("")
    parts.append("---\n")
    parts.append("*本报告由 大乐透AI娱乐分析助手 自动生成，仅供娱乐，不预测中奖。*\n")
    return "\n".join(parts)


def validate(rec_path: str, db_path: str, out_path: str) -> dict[str, Any]:
    recs = load_recs(rec_path)
    db = load_db(db_path)
    real_map = {it["issue"]: it for it in db.get("issues", [])}

    results: list[dict[str, Any]] = []
    for r in recs:
        issue = r["target_issue"]
        real = real_map.get(issue)
        if real is None:
            continue  # 该目标期号尚未开奖，跳过
        hit_f = len(set(r["front"]) & set(real["front"]))
        hit_b = len(set(r["back"]) & set(real["back"]))
        results.append({
            "target_issue": issue,
            "strategy": r["strategy"],
            "front": r["front"],
            "back": r["back"],
            "real_front": real["front"],
            "real_back": real["back"],
            "hit_front": hit_f,
            "hit_back": hit_b,
            "hit_total": hit_f + hit_b,
        })

    total = len(recs)
    validated = len(results)
    avg_hit = (sum(r["hit_total"] for r in results) / validated) if validated else 0.0
    summary = {"total": total, "validated": validated, "avg_hit": avg_hit}

    report = _build_report(results, summary)
    d = os.path.dirname(os.path.abspath(out_path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[validator] 累计推荐 {total} 组，已开奖可验证 {validated} 组，平均命中 {avg_hit:.2f} 个")
    if not results:
        print("[validator] 暂无已开奖记录（目标期号尚未开出），验证报告已生成占位。")
    return {"summary": summary, "results": results, "report_path": out_path}
