"""抓取中国体育彩票超级大乐透历史开奖数据。

数据源：500彩票网 大乐透历史数据页（结构稳定、无需登录）。
解析 HTML 表格得到：期号 / 前区5码 / 后区2码 / 开奖日期。

增量更新：若本地已有 JSON 数据库，则仅抓取「最新期号之后」的期数并合并，
避免每次全量抓取；数据库封顶保留最近 N 期（默认 1000）。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from .database import load, save


def _build_url(base_url: str, start: str, end: str) -> str:
    return f"{base_url}?start={start}&end={end}"


def _year_end_issue(latest: int) -> str:
    """给定最新 5 位期号（YYNNN），返回下一年年末期号，作为增量抓取上界（覆盖跨年）。"""
    yy = latest // 1000
    return f"{(yy + 1) % 100:02d}365"


def _to_ints(cells: list[str]) -> list[int]:
    out: list[int] = []
    for c in cells:
        c = c.strip()
        if c.isdigit():
            out.append(int(c))
    return out


def _find_data_table(soup: BeautifulSoup):
    """定位数据表：优先 id=tablelist，否则选择含‘期号’表头且首格为数字的数据表。"""
    table = soup.find("table", id="tablelist")
    if table is not None:
        return table
    for t in soup.find_all("table"):
        if "期号" in t.get_text() and t.find("td") and t.find("td").get_text(strip=True).isdigit():
            return t
    return None


def _parse_rows(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_data_table(soup)
    if table is None:
        raise RuntimeError("未找到数据表格，可能页面结构变化或请求被拦截")

    issues: list[dict[str, Any]] = []
    date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
    for tr in table.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 14:
            continue
        issue = tds[0]
        # 期号为 5 位数字（如 26092），过滤表头/子表头行
        if not (issue.isdigit() and len(issue) == 5):
            continue
        # 位置法：期号后 5 列为前区、再 2 列为后区
        front = _to_ints(tds[1:6])
        back = _to_ints(tds[6:8])
        if len(front) != 5 or len(back) != 2:
            continue
        if not all(1 <= n <= 35 for n in front):
            continue
        if not all(1 <= n <= 12 for n in back):
            continue
        date_td = next((t for t in tds if date_re.fullmatch(t)), "")
        issues.append({"issue": issue, "date": date_td, "front": front, "back": back})
    return issues


def _fetch_range(base_url: str, start: str, end: str, timeout: int, user_agent: str) -> list[dict[str, Any]]:
    """按 5 位期号范围（start~end）抓取并解析，返回降序排列的期号列表。"""
    url = _build_url(base_url, start, end)
    headers = {"User-Agent": user_agent}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.encoding = resp.apparent_encoding or "utf-8"
    resp.raise_for_status()
    issues = _parse_rows(resp.text)
    if not issues:
        raise RuntimeError("解析到 0 条记录，请检查数据源可用性")
    issues.sort(key=lambda x: x["issue"], reverse=True)
    return issues


def fetch(recent_issues: int, base_url: str, timeout: int, user_agent: str) -> list[dict[str, Any]]:
    """全量抓取：覆盖最近约 8 年，返回最近 recent_issues 期（首次运行使用）。"""
    year = datetime.now().year
    # 大乐透每年约 150 期；recent_issues=1000 需约 7 年历史，从 (year-7) 年起覆盖
    start = f"{(year - 7) % 100:02d}001"
    end = f"{year % 100:02d}365"
    issues = _fetch_range(base_url, start, end, timeout, user_agent)
    return issues[:recent_issues]


def run(config: dict[str, Any], db_path: str) -> dict[str, Any]:
    """抓取入口：有缓存则增量更新，无缓存则全量抓取；数据库封顶 recent_issues 期。"""
    sc = config["scrape"]
    recent = sc["recent_issues"]
    base_url = sc["base_url"]
    timeout = sc["timeout"]
    ua = sc["user_agent"]

    db = load(db_path)
    existing = db.get("issues", [])

    if existing:
        latest = max(int(it["issue"]) for it in existing)
        print(f"已有数据：{len(existing)}期")
        print(f"发现最新：{latest}")
        start = str(latest)
        end = _year_end_issue(latest)
        print(f"抓取范围：{start} ~ {end}（增量）")
        issues = _fetch_range(base_url, start, end, timeout, ua)
        new_ones = [it for it in issues if int(it["issue"]) > latest]
        print(f"新增：{len(new_ones)}期")
        db = save(db_path, new_ones, source="500", max_issues=recent)
    else:
        print("未检测到本地数据库，执行首次全量抓取……")
        issues = fetch(recent, base_url, timeout, ua)
        print(f"首次抓取：{len(issues)}期")
        db = save(db_path, issues, source="500", max_issues=recent)

    print("数据库更新完成。")
    return db
