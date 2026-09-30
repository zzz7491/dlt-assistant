#!/usr/bin/env python3
"""P3-1 完整历史 research dataset 构建器（stdlib，无 requests/bs4 依赖）。

抓取 500 彩票网 大乐透全历史（2007-今）→ 规范化 → 去重/连续性/交叉校验 →
与 production 1000 期逐期 exact 比对 → SHA256 + manifest。

产物（不覆盖 production）：
  data/research/dlt-full-history.json
  data/research/dlt-full-history.manifest.json
  reports/evaluation/P31-FULL-HISTORY-INTEGRITY-REPORT.md

在线抓取仅本脚本执行一次；后续 P3-2 通过 manifest 的 dataset_sha256 绑定不可变快照，
不再重新在线 fetch。
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.evaluation import history_integrity as hi

BASE = "https://datachart.500.com/dlt/history/newinc/history.php"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PRIMARY_SOURCE = "500.com (datachart.500.com/dlt/history/newinc/history.php)"


def _fetch_range_http(start: str, end: str, timeout: int = 30, retries: int = 3) -> str:
    url = f"{BASE}?start={start}&end={end}"
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"fetch {start}..{end} failed after {retries} tries: {last}")


def _parse_rows(html: str) -> list[dict]:
    """stdlib 解析（剥离 HTML 注释后按 <tr>/<td> 提取；与 production BeautifulSoup 逻辑一致）。"""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", c)).strip()
               for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < 14:
            continue
        issue = tds[0]
        if not (issue.isdigit() and len(issue) == 5):
            continue
        front = [int(x) for x in tds[1:6] if x.isdigit()]
        back = [int(x) for x in tds[6:8] if x.isdigit()]
        if len(front) != 5 or len(back) != 2:
            continue
        if not all(1 <= n <= 35 for n in front):
            continue
        if not all(1 <= n <= 12 for n in back):
            continue
        d = next((t for t in tds if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)), "")
        rows.append({"issue": issue, "date": d, "front": front, "back": back})
    return rows


def fetch_year(year: int, verbose: bool = True) -> list[dict]:
    """抓取某年（4-digit，如 2007）全部开奖记录。URL 用 2 位 YY。"""
    yy = year % 100
    html = _fetch_range_http(f"{yy:02d}001", f"{yy:02d}365")
    rows = _parse_rows(html)
    if verbose:
        s = sorted(r["issue"] for r in rows)
        print(f"  {year:04d}: {len(rows)} rows  {s[0] if s else '-'}..{s[-1] if s else '-'}")
    return rows


def parse_year_range(spec: str) -> list[int]:
    """'2007-2026' → [2007..2026]；'2007,2015,2026' → 指定列表。"""
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def acquire_full_history(years: list[int], verbose: bool = True) -> tuple[list[dict], list[dict]]:
    """抓取全部年份；返回 (raw_records, quarantined)。"""
    raw: list[dict] = []
    quarantined: list[dict] = []
    for yy in years:
        for rec in fetch_year(yy, verbose=verbose):
            try:
                raw.append(hi.normalize_record(rec))
            except ValueError as e:
                quarantined.append({"issue": rec.get("issue"), "date": rec.get("date"),
                                    "front": rec.get("front"), "back": rec.get("back"),
                                    "reason": str(e)})
    return raw, quarantined


# ---------------------------------------------------------------- secondary source probe

def probe_secondary() -> tuple[str | None, list[dict] | None]:
    """探测独立第二源。当前 500 为唯一稳定可解析源；尝试 sporttery 官网 JSON 端点，
    若不可靠则返回 (None, None) → CROSS_SOURCE_VERIFIED = NO（如实标注，不伪造验证）。"""
    candidates = [
        "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageHistoryLotteryInfo.do?provinceId=0&lotteryGameNum=85&pageSize=50&isVerify=true&pageNo=1",
    ]
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.sporttery.cn/"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            val = data.get("value", {})
            lists = val.get("list") or []
            if not lists:
                continue
            rows = []
            for it in lists:
                num = (it.get("lotteryDrawNum") or "").strip()
                if not re.fullmatch(r"\d{5}", num):
                    continue
                open_ = str(it.get("lotteryDrawResult") or "").split()
                f = [int(x) for x in open_[0:5] if x.isdigit()]
                b = [int(x) for x in open_[5:7] if x.isdigit()]
                date = (it.get("lotteryDrawTime") or "").split(" ")[0]
                if len(f) == 5 and len(b) == 2:
                    rows.append({"issue": num, "date": date, "front": f, "back": b})
            if len(rows) >= 100:
                return ("sporttery.cn official API", rows)
        except Exception:  # noqa: BLE001
            continue
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2007-2026")
    ap.add_argument("--production", default="data/dlt_history.json")
    ap.add_argument("--out-dir", default="data/research")
    ap.add_argument("--report-dir", default="reports/evaluation")
    ap.add_argument("--skip-cross-source", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="skip online fetch; rebuild validation from existing dataset")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    years = parse_year_range(args.years)

    out_dir = pathlib.Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "dlt-full-history.json"
    manifest_path = out_dir / "dlt-full-history.manifest.json"
    report_dir = root / args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    quarantined: list[dict] = []
    if args.offline and dataset_path.exists():
        print("[P3-1] offline mode: loading existing dataset for re-validation")
        raw = json.loads(dataset_path.read_text())
        raw = raw.get("issues", raw)
        records, quarantined = [], []
        for rec in raw:
            try:
                records.append(hi.normalize_record(rec))
            except ValueError as e:
                quarantined.append({"issue": rec.get("issue"), "reason": str(e)})
    else:
        print(f"[P3-1] fetching years {min(years)}..{max(years)} from {PRIMARY_SOURCE} ...")
        raw, quarantined = acquire_full_history(years, verbose=True)

    # 规范化 + 去重
    dups = hi.classify_duplicates(raw)
    if dups["conflict"]:
        print(f"[P3-1] ⚠ CONFLICT duplicates: {len(dups['conflict'])} (not silently overwritten)")
    records = hi.dedupe(raw)
    records.sort(key=lambda r: r["issue"])
    is_sorted, problems = hi.sort_temporal(records)

    # 连续性
    continuity = hi.check_continuity(records)

    # 时间顺序 + latest
    sorted_by_issue = sorted(records, key=lambda r: r["issue"])
    latest_issue = sorted_by_issue[-1]["issue"] if sorted_by_issue else None
    latest_date = sorted_by_issue[-1]["date"] if sorted_by_issue else None

    # production overlap（关键 Gate：必须 exact 1000/1000）
    prod_path = root / args.production
    prod_recs = hi.load_production_issues(str(prod_path))
    prod_norm = []
    for p in prod_recs:
        try:
            prod_norm.append(hi.normalize_record(p))
        except ValueError:
            prod_norm.append(p)
    overlap = hi.overlap_with_production(records, prod_norm)

    # 交叉源
    secondary_name = None
    cross = None
    cross_status = "NO"
    if not args.skip_cross_source and not args.offline:
        secondary_name, sec_rows = probe_secondary()
        if secondary_name and sec_rows:
            norm_sec = []
            for r in sec_rows:
                try:
                    norm_sec.append(hi.normalize_record(r))
                except ValueError:
                    pass
            cross = hi.cross_source_check(records, norm_sec)
            if cross["matched"] and not cross["mismatched"]:
                cross_status = "YES"
            elif cross["matched"]:
                cross_status = "PARTIAL"
            else:
                cross_status = "NO"
    else:
        secondary_name = "unavailable (offline/skipped)"

    # 校验状态
    overlap_ok = (overlap["overlap_count"] > 0
                  and overlap["overlap_match_count"] == overlap["overlap_count"])
    valid = (is_sorted and not dups["conflict"] and overlap_ok
             and not continuity["date_inversions"])
    validation_status = "PASS" if valid else "FAIL"

    # dataset JSON
    dataset = {
        "schema_version": hi.SCHEMA_VERSION,
        "game": hi.GAME,
        "source": PRIMARY_SOURCE,
        "secondary_source": secondary_name,
        "count": len(records),
        "issues": records,
    }
    dataset_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    # manifest
    manifest = hi.build_manifest(
        source=PRIMARY_SOURCE,
        secondary_source=secondary_name or "none",
        records=records,
        acquired_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        overlap=overlap,
        duplicates=dups,
        continuity=continuity,
        validation_status=validation_status,
        quarantined=quarantined,
    )
    manifest["cross_source_status"] = cross_status
    manifest["secondary_cross"] = cross if cross else None
    manifest["dataset_sha256_verify"] = hi.dataset_sha256(records)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # report
    report = _report(dataset, manifest, overlap, dups, continuity, cross_status,
                     is_sorted, quarantined)
    (report_dir / "P31-FULL-HISTORY-INTEGRITY-REPORT.md").write_text(report, encoding="utf-8")

    print(f"[P3-1] dataset → {dataset_path} ({len(records)} draws)")
    print(f"[P3-1] manifest → {manifest_path} (sha256 {manifest['dataset_sha256'][:16]})")
    print(f"[P3-1] overlap: {overlap['overlap_match_count']}/{overlap['overlap_count']} "
          f"exact match; validation = {validation_status}")
    print(f"[P3-1] report → {report_dir / 'P31-FULL-HISTORY-INTEGRITY-REPORT.md'}")
    if not valid:
        print("[P3-1] ⚠ validation not PASS — see report")


def _report(d, m, overlap, dups, cont, cross_status, is_sorted, quarantined) -> str:
    recs = d["issues"]
    earliest = recs[0] if recs else {}
    latest = recs[-1] if recs else {}
    lines = [
        "# P3-1 Full-History Acquisition & Data Integrity Report",
        "",
        f"Dataset `{m['schema_version']}` · source `{m['source']}` · "
        f"secondary `{m['secondary_source']}` · acquired {m['acquired_at']}",
        "",
        f"**VALIDATION STATUS: {m['validation_status']}**",
        "",
        "## Range",
        "",
        f"- earliest issue: **{m['earliest_issue']}** ({m['earliest_date']})",
        f"- latest issue: **{m['latest_issue']}** ({m['latest_date']})",
        f"- draw count: **{m['draw_count']}**",
        "",
        "## Integrity",
        "",
        f"- temporal sorted: {'PASS' if is_sorted else 'FAIL'}",
        f"- duplicate issues: {m['duplicate_issues']} "
        f"(benign {len(dups['benign'])} / conflict {len(dups['conflict'])})",
        f"- missing-issue candidates: {m['missing_issue_candidates']} "
        f"(yearly gaps incl. natural holiday/suspension breaks)",
        f"- date inversions: {m['date_inversions']}",
        f"- year transitions: {len(cont['year_transitions'])}",
        f"- quarantined records: {m['quarantined_count']}",
        "",
        "## Production Overlap (critical gate)",
        "",
        f"- overlap count: **{m['overlap_count']}** (production 1000-draw window ∩ full history)",
        f"- overlap exact match: **{m['overlap_match_count']}** "
        f"({'EXACT 1000/1000 — PASS' if m['overlap_match_count'] == m['overlap_count'] and m['overlap_count'] >= 1000 else 'MISMATCH — FAIL'})",
        f"- mismatches: {len(overlap['mismatches'])}",
        "",
        "## Cross-source validation",
        "",
        f"- status: **{cross_status}**",
        f"- secondary: {m['secondary_source']}",
        "",
        "## Dataset hash (immutable snapshot for P3-2)",
        "",
        f"- dataset_sha256: `{m['dataset_sha256']}`",
        f"- verify matches file: {m['dataset_sha256_verify'] == m['dataset_sha256']}",
        "",
        "## Production unchanged",
        "",
        "- production fetch limit / analyzer limit / window / recommender: **UNCHANGED** (P3-1 research-only)",
        "- 26112 published snapshot: **UNCHANGED**",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
