"""Incrementally archive DLT prize notices from a provincial sports lottery authority.

The number-only history stays independent. A notice is accepted only when its
issue, date and seven drawn numbers agree with the existing history record.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

INDEX_URL = "https://www.js-lottery.com/wfzq/dlt/data"
ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data/dlt_history.json"
OUTPUT = ROOT / "public/data/draw_details.json"
LEVELS = ["一", "二", "三", "四", "五", "六", "七"]


def integer(value: str) -> int:
    return int(value.replace(",", ""))


def listing(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"])
        text = row.get_text(" ", strip=True)
        match = re.search(r"\b(\d{5})\b", text)
        link = row.find("a", string=lambda x: bool(x and "详细" in x))
        if match and link and link.get("href"):
            url = urljoin(INDEX_URL, link["href"])
            if urlparse(url).hostname == "www.js-lottery.com":
                result[match.group(1)] = url
    return result


def parse_notice(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    issue_m = re.search(r"超级大乐透第(\d{5})期开奖公告", text)
    date_m = re.search(r"开奖日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    sales_m = re.search(r"本期全国销售金额[：:]\s*([\d,]+)元", text)
    pool_m = re.search(r"([\d,]+(?:\.\d{1,2})?)元奖金滚入下期奖池", text)
    deadline_m = re.search(r"本期兑奖截止日为(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if not all((issue_m, date_m, sales_m, pool_m)):
        raise ValueError("notice metadata incomplete")
    date = "-".join((date_m[1], date_m[2].zfill(2), date_m[3].zfill(2)))
    deadline = ("-".join((deadline_m[1], deadline_m[2].zfill(2), deadline_m[3].zfill(2)))
                if deadline_m else None)

    draw_row = next((tr for tr in soup.select("tr")
                     if "本期开奖号码" in tr.get_text(" ", strip=True)), None)
    if draw_row is None:
        raise ValueError("missing drawn numbers")
    cells = [td.get_text(" ", strip=True) for td in draw_row.find_all(["td", "th"])]
    groups = [re.findall(r"\b\d{2}\b", c) for c in cells]
    if len(groups) < 3 or len(groups[-2]) != 5 or len(groups[-1]) != 2:
        raise ValueError("invalid drawn numbers")
    front, back = [int(x) for x in groups[-2]], [int(x) for x in groups[-1]]

    prizes = {f"{level}等奖": {} for level in LEVELS}
    current = None
    for tr in soup.select("tr"):
        line = tr.get_text(" ", strip=True)
        found = re.search(r"([一二三四五六七])等奖", line)
        if found:
            current = f"{found[1]}等奖"
        if current is None:
            continue
        count = re.search(r"([\d,]+)\s*注", line)
        money = re.findall(r"([\d,]+)\s*元", line)
        if not count:
            continue
        if not money and integer(count[1]) != 0:
            continue
        item = {"winners": integer(count[1]),
                "per_ticket_yuan": integer(money[0]) if len(money) > 1 else None,
                "total_yuan": integer(money[-1]) if money else 0}
        kind = "additional" if "追加" in line else "basic"
        if current in ("一等奖", "二等奖"):
            prizes[current][kind] = item
        else:
            prizes[current] = item
    if any(not prizes[level] for level in prizes):
        raise ValueError("incomplete prize tiers")
    return {
        "issue": issue_m[1], "date": date, "front": front, "back": back,
        "sales_yuan": integer(sales_m[1]), "jackpot_yuan": pool_m[1],
        "claim_deadline": deadline, "prizes": prizes, "source_url": url,
        "source_name": "江苏省体育彩票管理中心",
    }


def run() -> int:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    by_issue = {str(x["issue"]): x for x in history["issues"]}
    old = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"issues": []}
    stored = {str(x["issue"]): x for x in old["issues"]}
    session = requests.Session()
    session.headers["User-Agent"] = "DLT archival research (public lottery notices)"
    response = session.get(INDEX_URL, timeout=20)
    response.raise_for_status()
    links = listing(response.text)
    if not links:
        raise ValueError("official listing yielded no detail links")
    added = 0
    for issue, url in links.items():
        if issue not in by_issue or issue in stored:
            continue
        response = session.get(url, timeout=20)
        response.raise_for_status()
        notice = parse_notice(response.text, url)
        history_row = by_issue[issue]
        if (notice["issue"] != issue or notice["date"] != history_row["date"]
                or notice["front"] != history_row["front"]
                or notice["back"] != history_row["back"]):
            raise ValueError(f"official/history mismatch at {issue}")
        stored[issue] = notice
        added += 1
    if added:
        payload = {"schema_version": 1, "updated_at": datetime.now(timezone.utc).isoformat(),
                   "issues": [stored[key] for key in sorted(stored)]}
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temp = OUTPUT.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(OUTPUT)
    print(f"official details: {added} new; {len(stored)} archived; listing {len(links)}")
    return added


if __name__ == "__main__":
    run()
