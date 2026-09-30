"""P3-1 大乐透完整历史数据 — 规范化 / 完整性 / 去重 / 连续性 / 交叉校验 / 哈希。

纯 stdlib 实现（无 requests/bs4 依赖），供 research dataset 构建与后续 P3-2 窗口实验
引用（通过 dataset_sha256 绑定不可变快照）。

设计原则（任务书）：
  - 不自动"修复"可疑开奖数据；异常 → quarantine/error 记录。
  - 冲突不静默覆盖。
  - 用真实期号规则（YYNNN）而非整数 +1 判断连续性。
  - 1000 cap 属于 production；本模块只处理 research full-history，不改 production。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

# 大乐透规则常量
FRONT_RANGE = (1, 35)
FRONT_N = 5
BACK_RANGE = (1, 12)
BACK_N = 2

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISSUE_RE = re.compile(r"^\d{5}$")

SCHEMA_VERSION = "p31-full-history-v1"
GAME = "cslottery-super-lottery (dlt)"


# ---------------------------------------------------------------- 基础校验

def normalize_issue(issue: str | int) -> str:
    """规范化期号为 5 位字符串（YYNNN）。非法抛 ValueError。"""
    s = str(issue).strip()
    if not _ISSUE_RE.fullmatch(s):
        raise ValueError(f"invalid issue: {issue!r}")
    return s


def issue_year(issue: str) -> int:
    return 2000 + int(normalize_issue(issue)[:2])


def issue_seq(issue: str) -> int:
    """年内期序（001..3xx）。"""
    return int(normalize_issue(issue)[2:])


def normalize_record(rec: dict[str, Any]) -> dict[str, Any]:
    """规范化单条开奖记录为 canonical form：

      {issue(str 5位), date(YYYY-MM-DD), front(sorted 5 unique int in 1..35),
       back(sorted 2 unique int in 1..12)}

    不合法（缺字段/超范围/重复/数量不对）→ 抛 ValueError（调用方记录为 quarantine）。
    """
    issue = normalize_issue(rec["issue"])
    date = str(rec.get("date", "")).strip()
    if not _DATE_RE.fullmatch(date):
        # 无法解析日期 → 记录为异常（不静默丢弃，date 保留原值并标记）
        raise ValueError(f"unparseable date {rec.get('date')!r} for {issue}")
    front = sorted(int(x) for x in rec.get("front", []))
    back = sorted(int(x) for x in rec.get("back", []))
    if len(front) != FRONT_N:
        raise ValueError(f"{issue}: front count {len(front)} != {FRONT_N}")
    if len(back) != BACK_N:
        raise ValueError(f"{issue}: back count {len(back)} != {BACK_N}")
    if len(set(front)) != FRONT_N:
        raise ValueError(f"{issue}: duplicate in front {front}")
    if len(set(back)) != BACK_N:
        raise ValueError(f"{issue}: duplicate in back {back}")
    if not all(FRONT_RANGE[0] <= x <= FRONT_RANGE[1] for x in front):
        raise ValueError(f"{issue}: front out of range {front}")
    if not all(BACK_RANGE[0] <= x <= BACK_RANGE[1] for x in back):
        raise ValueError(f"{issue}: back out of range {back}")
    return {"issue": issue, "date": date, "front": front, "back": back}


# ---------------------------------------------------------------- 去重 / 冲突

def classify_duplicates(records: list[dict]) -> dict[str, Any]:
    """检测重复期号。

    records: 已规范化记录列表（同 issue 可能多条）。
    返回：
      benign: 同 issue 且号码完全一致（源重复，可去重）
      conflict: 同 issue 但号码/日期不一致（source inconsistency，不静默）
      duplicate_issues: {issue: count}
    """
    by_issue: dict[str, list[dict]] = {}
    for r in records:
        by_issue.setdefault(r["issue"], []).append(r)
    duplicate_issues = {k: len(v) for k, v in by_issue.items() if len(v) > 1}
    benign: list[str] = []
    conflict: list[dict] = []
    for issue, grp in by_issue.items():
        if len(grp) == 1:
            continue
        uniq = {(tuple(r["front"]), tuple(r["back"]), r["date"]) for r in grp}
        if len(uniq) == 1:
            benign.append(issue)
        else:
            conflict.append({
                "issue": issue,
                "variants": [{"front": r["front"], "back": r["back"], "date": r["date"]}
                             for r in grp],
            })
    return {
        "duplicate_issues": duplicate_issues,
        "benign": sorted(benign),
        "conflict": sorted(conflict, key=lambda x: x["issue"]),
    }


def dedupe(records: list[dict]) -> list[dict]:
    """按期号去重（同 issue 取其一；仅当无冲突时安全）。返回按期号升序。"""
    best: dict[str, dict] = {}
    for r in records:
        best.setdefault(r["issue"], r)
    return [best[i] for i in sorted(best)]


# ---------------------------------------------------------------- 连续性

def year_issue_sequence(year: int) -> list[str]:
    """某年的合法期号序列（001..该年实际最大期号）。

    注意：大乐透每年期号从 001 递增，季末/年末会有不连续（春节/休市），
    因此这里不假设连续；连续性检查用"当年出现过的期号"做集合比对。
    """
    return [f"{year % 100:02d}{n:03d}" for n in range(1, 366)]


def check_continuity(sorted_recs: list[dict]) -> dict[str, Any]:
    """按真实期号规则检查连续性（不假设整数 +1）。

    返回：
      missing_issue_candidates: 每个年内，若某序号在相邻出现序号之间跳过且跳过的序号
          在当年范围内未出现 → 候选缺失（含春节/休市自然间隔，需人工确认，非硬错）。
      unexpected_jumps: 年内序号出现 >1 的跳跃（降序检测后按升序）
      date_inversions: 期号升序但日期非升序（> 前一期）的位置
      year_transitions: 跨年处记录（07->08 等）
    """
    by_year: dict[int, list[str]] = {}
    for r in sorted_recs:
        y = issue_year(r["issue"])
        by_year.setdefault(y, []).append(r["issue"])

    missing_candidates: list[dict] = []
    jumps: list[dict] = []
    for y in sorted(by_year):
        seqs = sorted(issue_seq(i) for i in by_year[y])
        # 检测跳跃
        for a, b in zip(seqs, seqs[1:]):
            if b - a > 1:
                gap = [f"{y % 100:02d}{n:03d}" for n in range(a + 1, b)]
                missing_candidates.append({
                    "year": y, "from_seq": a, "to_seq": b,
                    "candidate_issues": gap, "note": "may be natural break (holiday/suspension)",
                })
                jumps.append({"year": y, "from_seq": a, "to_seq": b})

    # 日期逆序（期号升序下日期应非降序）
    date_inversions = []
    for i in range(1, len(sorted_recs)):
        prev, cur = sorted_recs[i - 1], sorted_recs[i]
        if issue_year(cur["issue"]) == issue_year(prev["issue"]) and cur["date"] < prev["date"]:
            date_inversions.append({"from": prev["issue"], "to": cur["issue"],
                                   "prev_date": prev["date"], "cur_date": cur["date"]})

    year_transitions = [
        {"from": sorted_recs[i - 1]["issue"], "to": sorted_recs[i]["issue"],
         "from_year": issue_year(sorted_recs[i - 1]["issue"]),
         "to_year": issue_year(sorted_recs[i]["issue"])}
        for i in range(1, len(sorted_recs))
        if issue_year(sorted_recs[i]["issue"]) != issue_year(sorted_recs[i - 1]["issue"])
    ]
    return {
        "missing_issue_candidates": missing_candidates,
        "unexpected_jumps": jumps,
        "date_inversions": date_inversions,
        "year_transitions": year_transitions,
    }


# ---------------------------------------------------------------- overlap 校验

def overlap_with_production(full_records: list[dict],
                            production_records: list[dict]) -> dict[str, Any]:
    """full-history 与 production 1000 期在重叠区逐期比较（issue/date/front/back）。

    要求：重叠区每一条都 exact match（P3-1 STEP 9 关键 Gate）。
    返回 {overlap_count, overlap_match_count, mismatches:[...]}。
    """
    prod_by = {r["issue"]: r for r in production_records}
    mismatches = []
    match = 0
    for r in full_records:
        if r["issue"] in prod_by:
            p = prod_by[r["issue"]]
            ok = (list(p.get("front", [])) == r["front"]
                  and list(p.get("back", [])) == r["back"]
                  and str(p.get("date", "")) == r["date"])
            if ok:
                match += 1
            else:
                mismatches.append({
                    "issue": r["issue"],
                    "full": {"front": r["front"], "back": r["back"], "date": r["date"]},
                    "prod": {"front": p.get("front"), "back": p.get("back"), "date": p.get("date")},
                })
    overlap_count = sum(1 for r in full_records if r["issue"] in prod_by)
    return {"overlap_count": overlap_count, "overlap_match_count": match,
            "mismatches": mismatches}


def cross_source_check(a: list[dict], b: list[dict]) -> dict[str, Any]:
    """两个源在交集上的逐期比较（STEP 8）。matched/mismatched/missing-in-A/missing-in-B。"""
    a_by = {r["issue"]: r for r in a}
    b_by = {r["issue"]: r for r in b}
    common = set(a_by) & set(b_by)
    matched, mismatched = 0, []
    for issue in common:
        ra, rb = a_by[issue], b_by[issue]
        if (list(ra.get("front", [])) == list(rb.get("front", []))
                and list(ra.get("back", [])) == list(rb.get("back", []))
                and str(ra.get("date", "")) == str(rb.get("date", ""))):
            matched += 1
        else:
            mismatched.append({"issue": issue, "a": ra, "b": rb})
    return {
        "matched": matched,
        "mismatched": mismatched,
        "missing_in_a": sorted(set(b_by) - set(a_by)),
        "missing_in_b": sorted(set(a_by) - set(b_by)),
    }


# ---------------------------------------------------------------- hash / manifest

def dataset_sha256(records: list[dict]) -> str:
    """对规范化记录（按期号升序）计算确定性 SHA256。"""
    canonical = sorted(records, key=lambda r: r["issue"])
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_manifest(*, source: str, secondary_source: str,
                   records: list[dict], acquired_at: str,
                   overlap: dict[str, Any],
                   duplicates: dict[str, Any],
                   continuity: dict[str, Any],
                   validation_status: str,
                   quarantined: list[dict] | None = None) -> dict[str, Any]:
    """P3-1 STEP 11/12 manifest（含 dataset_sha256，供 P3-2 绑定不可变快照）。"""
    recs = sorted(records, key=lambda r: r["issue"])
    dates = [r["date"] for r in recs]
    return {
        "schema_version": SCHEMA_VERSION,
        "game": GAME,
        "source": source,
        "secondary_source": secondary_source,
        "acquired_at": acquired_at,
        "earliest_issue": recs[0]["issue"] if recs else None,
        "latest_issue": recs[-1]["issue"] if recs else None,
        "earliest_date": dates[0] if dates else None,
        "latest_date": dates[-1] if dates else None,
        "draw_count": len(recs),
        "dataset_sha256": dataset_sha256(recs),
        "overlap_count": overlap.get("overlap_count"),
        "overlap_match_count": overlap.get("overlap_match_count"),
        "duplicate_issues": len(duplicates.get("duplicate_issues", {})),
        "conflicts": len(duplicates.get("conflict", [])),
        "missing_issue_candidates": len(continuity.get("missing_issue_candidates", [])),
        "date_inversions": len(continuity.get("date_inversions", [])),
        "quarantined_count": len(quarantined or []),
        "validation_status": validation_status,
    }


def load_production_issues(path: str) -> list[dict]:
    """读取 production dlt_history.json 的 issues（不动 production 文件）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("issues", []) if isinstance(data, dict) else data


def sort_temporal(records: list[dict]) -> tuple[bool, list[str]]:
    """验证记录按期号升序；返回 (is_sorted, problems)。"""
    problems = []
    for i in range(1, len(records)):
        prev, cur = records[i - 1], records[i]
        a, b = int(prev["issue"]), int(cur["issue"])
        if a >= b:
            problems.append(f"{prev['issue']} !< {cur['issue']}")
    return (len(problems) == 0), problems
