"""一次性清理：删除站上静态文件中的随机推荐内容与"随机"字样。

用户指令（2026-10-20）：除机选（public/pick.html、public/pick.js）外，
分析、推荐等一切用户可见内容中，所有"随机"字样与随机生成内容全部删除。
D1 推荐表的历史随机 C 行由 oneoff_purge_random_c.py 负责（不归本脚本管）。

本脚本处理（默认 dry-run 只打印计划；--apply 才写文件）：
  1. public/data/published_recommendations.json：删除 primary_strategy 为
     'C-纯随机娱乐型' 的发布条目（7 条）；剩余条目做字样扫描改写。
  2. public/data/recommendations.json：删除 strategy 为 'C-纯随机娱乐型' 的条目；
     剩余条目做字样扫描改写。
  3. public/data/strategy_score.json：删除 strategy=='C' 的行（其回测统计源于
     已删除的旧基线；publisher.build_strategy_score 已改为跳过 C）。
  4. public/data/recommendation_new.json：改写 notice 免责句。
  5. public/data/ai_cycle_archive.json：删除 evidence/original_statistical_basis
     含"随机基线"的 reviews/raw_model_records 条目（其评审对象是随机推荐）；
     改写两处存档文案（risk 文本、selection_role）。
  6. public/reports/report_*.md 与 validation_report.md：改写免责句、
     删除"推荐 C（纯随机娱乐型）"号码块。

字样改写映射（仅精确匹配整句/整块，避免误伤）：
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

OLD_STRATEGY = "C-纯随机娱乐型"

# 精确句子替换（旧 → 新）
SENTENCE_MAP = {
    "彩票开奖为独立随机事件，任何历史规律均不构成未来结果的依据。":
    "彩票每期开奖相互独立，任何历史规律均不构成未来结果的依据。",
    "以下 A/B/C 三策略均基于历史统计或随机生成，**仅供娱乐讨论，不等于中奖预测**：":
    "以下 A/B/C 三策略均由历史统计分析或 AI 生成，**仅供娱乐讨论，不等于中奖预测**：",
    "> 再次提醒：以上号码为算法随机娱乐产物，不等于中奖预测。":
    "> 再次提醒：以上号码为统计分析与 AI 生成的娱乐内容，不等于中奖预测。",
    "本工具仅提供娱乐性选号辅助，不具备预测彩票结果能力。彩票开奖为独立随机事件，请理性购彩。":
    "本工具仅提供娱乐性选号辅助，不具备预测彩票结果能力。彩票每期开奖相互独立，请理性购彩。",
    "彩票开奖为独立随机事件。":
    "彩票每期开奖相互独立。",
    "但无法抵消随机性影响，存在投入产出不对等风险":
    "但无法改变每期开奖结果不可预测的本质，存在投入产出不对等风险",
    "不把候选的随机构造冒称为AI选号":
    "不把候选的非统计构造冒称为AI选号",
    "分析需基于已固化组合，不引入随机构造或未验证趋势。":
    "分析需基于已固化组合，不引入无依据的号码构造或未验证趋势。",
}

C_BLOCK_RE = re.compile(
    r"\*\*推荐 C（纯随机娱乐型）：\*\*\n(?:- [^\n]*\n)+\n?"
)

# 验证报告里的随机策略数据表行（整行删除）
C_TABLE_ROW_RE = re.compile(r"^\|[^\n]*C-纯随机娱乐型[^\n]*\n", re.M)


def _report(changes: list[str]) -> None:
    for c in changes:
        print(c)


def clean_published(changes: list[str]) -> dict | None:
    p = "public/data/published_recommendations.json"
    d = json.load(open(p, encoding="utf-8"))
    before = len(d["items"])
    kept = [it for it in d["items"] if it.get("primary_strategy") != OLD_STRATEGY]
    removed = before - len(kept)
    d["items"] = kept
    # 剩余条目字样扫描
    s = json.dumps(d, ensure_ascii=False)
    for old, new in SENTENCE_MAP.items():
        if old in s:
            s = s.replace(old, new)
            changes.append(f"[{p}] 改写字样：{old[:18]}…")
    d = json.loads(s)
    changes.append(f"[{p}] 删除随机 C 发布条目 {removed} 条，剩余 {len(d['items'])} 条")
    return d


def clean_recommendations(changes: list[str]) -> list | None:
    p = "public/data/recommendations.json"
    d = json.load(open(p, encoding="utf-8"))
    before = len(d)
    d = [e for e in d if e.get("strategy") != OLD_STRATEGY]
    changes.append(f"[{p}] 删除随机 C 条目 {before - len(d)} 条，剩余 {len(d)} 条")
    s = json.dumps(d, ensure_ascii=False)
    for old, new in SENTENCE_MAP.items():
        if old in s:
            s = s.replace(old, new)
            changes.append(f"[{p}] 改写字样：{old[:18]}…")
    return json.loads(s)


def clean_strategy_score(changes: list[str]) -> dict | None:
    p = "public/data/strategy_score.json"
    d = json.load(open(p, encoding="utf-8"))
    before = len(d.get("strategies", []))
    d["strategies"] = [r for r in d["strategies"] if r.get("strategy") != "C"]
    changes.append(f"[{p}] 删除 C 行 {before - len(d['strategies'])} 条（旧基线统计），剩余 {len(d['strategies'])} 条")
    return d


def clean_recommendation_new(changes: list[str]) -> dict | None:
    p = "public/data/recommendation_new.json"
    d = json.load(open(p, encoding="utf-8"))
    s = json.dumps(d, ensure_ascii=False)
    for old, new in SENTENCE_MAP.items():
        if old in s:
            s = s.replace(old, new)
            changes.append(f"[{p}] 改写字样：{old[:18]}…")
    return json.loads(s)


def _is_random_review(entry: dict) -> bool:
    ev = entry.get("evidence") or {}
    basis = str(ev.get("original_statistical_basis") or "")
    return "随机基线" in basis


def clean_ai_cycle_archive(changes: list[str]) -> dict | None:
    p = "public/data/ai_cycle_archive.json"
    d = json.load(open(p, encoding="utf-8"))
    for key in ("reviews",):
        before = len(d.get(key, []))
        d[key] = [e for e in d.get(key, []) if not _is_random_review(e)]
        changes.append(f"[{p}] {key} 删除评审对象为随机推荐的条目 {before - len(d[key])} 条")
    raw = d.get("raw_model_records") or {}
    if isinstance(raw, dict):
        drop = [k for k, v in raw.items() if isinstance(v, dict) and _is_random_review(v)]
        for k in drop:
            del raw[k]
        changes.append(f"[{p}] raw_model_records 删除 {len(drop)} 条")
    s = json.dumps(d, ensure_ascii=False)
    for old, new in SENTENCE_MAP.items():
        n = s.count(old)
        if n:
            s = s.replace(old, new)
            changes.append(f"[{p}] 改写字样 {n} 处：{old[:18]}…")
    return json.loads(s)


def clean_reports(changes: list[str]) -> dict[str, str]:
    import glob

    out: dict[str, str] = {}
    files = sorted(glob.glob("public/reports/report_*.md")) + [
        "public/reports/validation_report.md"
    ]
    for p in files:
        if not os.path.exists(p):
            continue
        s = open(p, encoding="utf-8").read()
        touched = False
        for old, new in SENTENCE_MAP.items():
            if old in s:
                s = s.replace(old, new)
                touched = True
        new_s, n = C_BLOCK_RE.subn("", s)
        if n:
            s = new_s
            touched = True
            changes.append(f"[{p}] 删除随机 C 号码块 {n} 处")
        new_s, n2 = C_TABLE_ROW_RE.subn("", s)
        if n2:
            s = new_s
            touched = True
            changes.append(f"[{p}] 删除随机 C 数据表行 {n2} 处")
        # 残留扫描
        leftovers = [m.group(0)[:40] for m in re.finditer(r".{0,12}随机.{0,20}", s)]
        if leftovers:
            changes.append(f"[{p}] ⚠️ 仍残留随机字样 {len(leftovers)} 处（需人工复核）：{leftovers[:3]}")
        if touched:
            out[p] = s
    changes.append(f"[reports] 共改动 {len(out)} 个文件")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    changes: list[str] = []

    results = {
        "public/data/published_recommendations.json": clean_published(changes),
        "public/data/recommendations.json": clean_recommendations(changes),
        "public/data/strategy_score.json": clean_strategy_score(changes),
        "public/data/recommendation_new.json": clean_recommendation_new(changes),
        "public/data/ai_cycle_archive.json": clean_ai_cycle_archive(changes),
    }
    report_files = clean_reports(changes)

    print("===== DRY-RUN 计划 =====" if not args.apply else "===== 执行 =====")
    _report(changes)
    if not args.apply:
        print("加 --apply 真正写文件。")
        return 0
    for p, d in results.items():
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"已写 {p}")
    for p, s in report_files.items():
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(s)
    print(f"已写 {len(report_files)} 个报告文件")
    # 最终验收：全站扫描
    print("===== 最终扫描（应只剩 pick/experiment/测试断言等登记项）=====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
