"""C-AI智能型出号：LLM 基于与 A/B 相同统计口径的统计摘要直接出号。

C 策略改为接 LLM 的真 AI 出号（2026-10-20 用户指令：推荐必须全部是分析产出）。

统计口径约束（用户 2026-10-20 纠正：不许自创窗口，必须复用现有默认口径）：
- 四彩种（双色球/福彩3D/排列三/排列五）：src/{ssq,fc3d,pl3,pl5}/stats.py
  的 frequency(rows, 100) + omission(rows) —— 近100期频率 + 全量遗漏，
  与 A/B 策略 generate_picks 所用口径完全一致。本模块不定义任何窗口
  数字，只消费调用方按现有口径算好的摘要 dict。
- 大乐透：src/analyzer.analyze() 的 hot/cold + *_recent_freq
  （config/settings.yaml 的 recent_window: 50，即近50期）+ 遗漏，
  与 _strategy_balanced/_strategy_hotcold 的输入完全同源。

通道复用大乐透 AI 配置（与 scripts/ai_cycle.py 一致）：
- DLT_AI_API_KEY → 回退 OPENROUTER_API_KEY
- DLT_AI_BASE_URL → 回退 OPENROUTER_BASE_URL → https://openrouter.ai/api/v1
- DLT_AI_MODEL → 回退 deepseek/deepseek-chat
无密钥 → 返回 None（调用方跳过 C）。调用失败（重试 1 次后仍失败）
→ 返回 None。失败则跳过该策略数。

仅用 Python 标准库（urllib），不新增依赖。
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

BASE_URL_FALLBACK = "https://openrouter.ai/api/v1"
MODEL_FALLBACK = "deepseek/deepseek-chat"
TIMEOUT_SECS = 60

# 各彩种出号规则（与现有代码的合法范围一致）
RULES = {
    "ssq": {
        "label": "双色球",
        "schema": '{"red": [6个1-33不重复红球，升序], "blue": 蓝球1-16}',
        "desc": "红球 6 个（1-33，不重复，升序），蓝球 1 个（1-16）。",
    },
    "dlt": {
        "label": "大乐透",
        "schema": '{"front": [5个1-35不重复前区，升序], "back": [2个1-12不重复后区，升序]}',
        "desc": "前区 5 个（1-35，不重复，升序），后区 2 个（1-12，不重复，升序）。",
    },
    "fc3d": {
        "label": "福彩3D",
        "schema": '{"digits": [百位, 十位, 个位]，每位0-9，可重复，按位置顺序}',
        "desc": "百/十/个位各 1 个数字（0-9，可重复，顺序即位置）。",
    },
    "pl3": {
        "label": "排列三",
        "schema": '{"digits": [百位, 十位, 个位]，每位0-9，可重复，按位置顺序}',
        "desc": "百/十/个位各 1 个数字（0-9，可重复，顺序即位置）。",
    },
    "pl5": {
        "label": "排列五",
        "schema": '{"digits": [万位, 千位, 百位, 十位, 个位]，每位0-9，可重复，按位置顺序}',
        "desc": "万/千/百/十/个位各 1 个数字（0-9，可重复，顺序即位置）。",
    },
}

# 各彩种统计口径说明（prompt 里如实声明，与现有代码一致）
CALIBER = {
    "ssq": "近100期频率（src/ssq/stats.py frequency(rows, 100)，与 A/B 同口径）+ 全量遗漏 + 最近10期开奖",
    "fc3d": "近100期分位频率（src/fc3d/stats.py frequency(rows, 100)，与 A/B 同口径）+ 全量遗漏 + 最近10期开奖",
    "pl3": "近100期分位频率（src/pl3/stats.py frequency(rows, 100)，与 A/B 同口径）+ 全量遗漏 + 最近10期开奖",
    "pl5": "近100期分位频率（src/pl5/stats.py frequency(rows, 100)，与 A/B 同口径）+ 全量遗漏 + 最近10期开奖",
    "dlt": "近50期频率与热冷（src/analyzer.analyze，config/settings.yaml recent_window: 50，与 A/B 同源）+ 遗漏 + 最近10期开奖",
}


def _env_chain() -> tuple[str | None, str, list[str]]:
    key = os.getenv("DLT_AI_API_KEY", "").strip() or os.getenv(
        "OPENROUTER_API_KEY", ""
    ).strip()
    base = (
        os.getenv("DLT_AI_BASE_URL", "").strip()
        or os.getenv("OPENROUTER_BASE_URL", "").strip()
        or BASE_URL_FALLBACK
    ).rstrip("/")
    model_env = os.getenv("DLT_AI_MODEL", "").strip()
    models = [model_env] if model_env else []
    if MODEL_FALLBACK not in models:
        models.append(MODEL_FALLBACK)
    return (key or None), base, models


def _build_prompt(game_id: str, target_issue: str, summary: dict) -> str:
    rule = RULES[game_id]
    summary_text = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    return (
        f"你是一位彩票统计分析助手。根据以下{RULES[game_id]['label']}历史统计摘要"
        f"（统计口径：{CALIBER[game_id]}），为目标期 {target_issue} 直接给出 1 组号码。\n"
        f"出号规则：{rule['desc']}\n"
        f"统计摘要：{summary_text}\n"
        "要求：\n"
        "1. 综合频率、遗漏、热冷与近期走势给出你认为最合理的一组号码；\n"
        "2. 只输出严格 JSON，格式为 " + rule["schema"] + "，不要输出任何解释、前后缀或 markdown 代码块；\n"
        "3. JSON 中的数字必须全部符合上面的出号规则。\n"
    )


def _build_trend_prompt(game_id: str, target_issue: str, trend: dict) -> str:
    rule = RULES[game_id]
    trend_text = json.dumps(trend, ensure_ascii=False, separators=(",", ":"))
    return (
        f"你是一位在彩票店看走势图的资深彩民，擅长看走势图研判号码。"
        f"下面是{RULES[game_id]['label']}最近 {trend.get('window', 30)} 期的走势图数据："
        f"逐期开奖（旧→新）、和值与跨度逐期序列（即和值/跨度曲线）、"
        f"以及每个号码的出号条（逐期 1=开出、0=未开出，按时间从旧到新，末尾是最新一期；"
        f"数字型为每个数位上每个数字的出号条）。\n"
        f"请像看走势图一样研判目标期 {target_issue}：看各号码出号条的疏密、连出与断档形态，"
        f"看和值/跨度曲线的走向与所处位置，结合最近几期的形态衔接，"
        f"给出你研判的 1 组号码。不要用频率统计或遗漏排名代替看图研判。\n"
        f"出号规则：{rule['desc']}\n"
        f"走势图数据：{trend_text}\n"
        "要求：\n"
        "1. 只输出严格 JSON，格式为 " + rule["schema"] + "，不要输出任何解释、前后缀或 markdown 代码块；\n"
        "2. JSON 中的数字必须全部符合上面的出号规则。\n"
    )


def _post_json(url: str, headers: dict, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    # 去掉可能的 markdown 代码块围栏
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except Exception:
        # 尝试截取第一个 {...} 块
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(text[start : end + 1])
        except Exception:
            return None
    return obj if isinstance(obj, dict) else None


def _validate(game_id: str, obj: dict) -> dict | None:
    def _ints(xs, lo, hi):
        if not isinstance(xs, list):
            return None
        out = []
        for x in xs:
            if isinstance(x, bool) or not isinstance(x, int):
                return None
            if not (lo <= x <= hi):
                return None
            out.append(x)
        return out

    if game_id == "ssq":
        red = _ints(obj.get("red"), 1, 33)
        blue = obj.get("blue")
        if red is None or len(red) != 6 or len(set(red)) != 6:
            return None
        if isinstance(blue, bool) or not isinstance(blue, int) or not (1 <= blue <= 16):
            return None
        return {"red": sorted(red), "blue": blue}
    if game_id == "dlt":
        front = _ints(obj.get("front"), 1, 35)
        back = _ints(obj.get("back"), 1, 12)
        if front is None or len(front) != 5 or len(set(front)) != 5:
            return None
        if back is None or len(back) != 2 or len(set(back)) != 2:
            return None
        return {"front": sorted(front), "back": sorted(back)}
    if game_id in ("fc3d", "pl3"):
        digits = _ints(obj.get("digits"), 0, 9)
        if digits is None or len(digits) != 3:
            return None
        return {"digits": digits}  # 位置顺序保留，不排序
    if game_id == "pl5":
        digits = _ints(obj.get("digits"), 0, 9)
        if digits is None or len(digits) != 5:
            return None
        return {"digits": digits}
    return None


def pick(game_id: str, target_issue: str | None, summary: dict) -> dict | None:
    """C-AI智能型出号。成功返回号码 dict；无密钥/失败返回 None（调用方跳过 C）。

    summary 由调用方按各彩种现有 A/B 统计口径构造（见模块 docstring），
    本函数只负责 prompt 组装、调用、校验。
    """
    return _call(game_id, target_issue, _build_prompt(game_id, str(target_issue or "?"), summary), "C-AI智能型")


def pick_trend(game_id: str, target_issue: str | None, trend: dict) -> dict | None:
    """走势AI型出号：AI 看走势图数据（src/common/trend_data 构造）直接研判出号。

    与 pick() 同通道、同校验；无密钥/失败返回 None（调用方跳过该策略）。
    """
    return _call(game_id, target_issue, _build_trend_prompt(game_id, str(target_issue or "?"), trend), "走势AI型")


def _call(game_id: str, target_issue: str | None, prompt: str, tag: str) -> dict | None:
    if game_id not in RULES:
        print(f"[ai_pick] 未知彩种 {game_id}，跳过 {tag}")
        return None
    key, base, models = _env_chain()
    if not key:
        print(f"[ai_pick] 未配置 DLT_AI_API_KEY/OPENROUTER_API_KEY，跳过 {tag}（不报错）")
        return None
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://dlt.mootlsv.com/",
        "X-Title": "dlt-assistant C-AI",
    }
    url = f"{base}/chat/completions"
    for model in models:
        for attempt in (1, 2):
            try:
                body = _post_json(
                    url,
                    headers,
                    {
                        "model": model,
                        "temperature": 0.2,
                        "max_tokens": 300,
                        "messages": [
                            {"role": "system", "content": "你只输出严格 JSON，不输出任何解释。"},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                choices = body.get("choices") or []
                text = (choices[0].get("message") or {}).get("content") if choices else ""
                obj = _extract_json(text)
                valid = _validate(game_id, obj) if obj else None
                if valid is not None:
                    print(f"[ai_pick] {game_id} target={target_issue} model={model} ok")
                    return valid
                print(
                    f"[ai_pick] {game_id} model={model} attempt={attempt} "
                    "返回格式非法，重试"
                )
            except urllib.error.HTTPError as e:
                # 401/402 鉴权/额度问题：换模型也无用，直接放弃
                print(f"[ai_pick] {game_id} model={model} HTTP {e.code}，停止重试")
                if e.code in (401, 402, 403):
                    return None
            except Exception as e:
                print(
                    f"[ai_pick] {game_id} model={model} attempt={attempt} "
                    f"异常 {type(e).__name__}，{'重试' if attempt == 1 else '放弃'}"
                )
    print(f"[ai_pick] {game_id} target={target_issue} 全部失败，跳过 C（失败则跳过该策略）")
    return None
