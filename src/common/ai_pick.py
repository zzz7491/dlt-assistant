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


def _env_chain(local: bool = False) -> tuple[str | None, str, list[str]]:
    if local:
        # C-AI智能型专用本地通道（2026-10-22 用户定混合方案）：配了
        # DLT_PICK_BASE_URL 就走本地模型（零费用）；未配则落回下方云端链。
        lbase = os.getenv("DLT_PICK_BASE_URL", "").strip().rstrip("/")
        if lbase:
            lkey = os.getenv("DLT_PICK_API_KEY", "").strip() or "ollama"
            lmodel = os.getenv("DLT_PICK_MODEL", "").strip()
            return lkey, lbase, ([lmodel] if lmodel else ["gemma3:27b"])
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
    if base.startswith("https://openrouter.ai") and MODEL_FALLBACK not in models:
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
        f"下面是{RULES[game_id]['label']}最近 {trend.get('window', 300)} 期的走势图数据："
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


def _post_json(url: str, headers: dict, payload: dict, timeout: int = TIMEOUT_SECS) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    return _call(game_id, target_issue, _build_prompt(game_id, str(target_issue or "?"), summary), "C-AI智能型", local=True)


SEGMENT_SIZE = 60


def _is_local_base(base: str) -> bool:
    return not base.startswith("https://openrouter.ai")


def _trend_segment(trend: dict, start: int, end: int) -> dict:
    """把走势 dict 切出 [start, end) 一段（逐期序列与每条出号条同步切）。"""
    seg = {"window": end - start}
    for k in ("draws", "sum_series", "span_series", "distinct_series"):
        if k in trend:
            seg[k] = trend[k][start:end]
    for k in ("main_strips", "sub_strips"):
        if k in trend:
            seg[k] = {n: s[start:end] for n, s in trend[k].items()}
    if "position_strips" in trend:
        seg["position_strips"] = [
            {d: s[start:end] for d, s in pos.items()} for pos in trend["position_strips"]
        ]
    return seg


def _headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://dlt.mootlsv.com/",
        "X-Title": "dlt-assistant C-AI",
        # 本地网关（Cloudflare）会拦 Python 默认 UA，必须带浏览器 UA
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    }


def _chat_text(key: str, base: str, models: list, prompt: str, max_tokens: int = 500) -> str | None:
    """纯文本调用（分段研判用）：逐模型尝试，返回 content 文本或 None。"""
    url = f"{base}/chat/completions"
    for model in models:
        for _attempt in (1, 2):
            try:
                body = _post_json(
                    url,
                    _headers(key),
                    {
                        "model": model,
                        "temperature": 0.3,
                        "max_tokens": max_tokens,
                        "messages": [
                            {"role": "system", "content": "你只输出研判要点文本，不输出其他内容。"},
                            {"role": "user", "content": prompt},
                        ],
                    },
                    timeout=100,
                )
                choices = body.get("choices") or []
                text = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
                if text:
                    return text
            except Exception:
                continue
    return None


def _segment_prompt(game_id: str, idx: int, total: int, seg: dict) -> str:
    rule = RULES[game_id]
    seg_text = json.dumps(seg, ensure_ascii=False, separators=(",", ":"))
    return (
        f"你是一位在彩票店看走势图的资深彩民。下面是{rule['label']}走势图的第 {idx + 1}/{total} 段"
        f"（本段 {seg.get('window', 0)} 期，逐期开奖旧→新、和值与跨度逐期序列、每个号码的出号条；"
        f"数字型为每个数位上每个数字的出号条）。\n"
        f"走势图数据：{seg_text}\n"
        "只输出本段的走势研判要点（不超过 200 字）：各号码/数位出号条的疏密、连出与断档形态，"
        "和值/跨度曲线的走向与位置，段末的形态衔接。不要出号，不要给最终号码。"
    )


def _pick_trend_segmented(game_id: str, target_issue: str, trend: dict) -> dict | None:
    """本地端点分段研判（2026-10-22 用户定）：300 期走势图整段直喂会超过
    本地网关单请求时限，故按 60 期一段逐段请 AI 研判要点，最后汇总各段
    要点 + 最近一段原始走势出号。任一段失败 → 整策略跳过（不回退）。"""
    key, base, models = _env_chain()
    if not key:
        print("[ai_pick] 未配置密钥，跳过 走势AI型（不报错）")
        return None
    n = int(trend.get("window") or len(trend.get("draws") or []))
    if n <= SEGMENT_SIZE:
        return _call(game_id, target_issue, _build_trend_prompt(game_id, target_issue, trend), "走势AI型")
    total = (n + SEGMENT_SIZE - 1) // SEGMENT_SIZE
    digests = []
    # 分段要点走非推理模型直出文本：推理模型会把 token 预算烧在隐藏思考上、
    # 正文为空（2026-10-22 #177 实测全灭）。可用 DLT_AI_DIGEST_MODEL 覆盖。
    digest_models = models
    if _is_local_base(base):
        digest_models = [os.environ.get("DLT_AI_DIGEST_MODEL") or "gemma3:27b"]
    for i in range(total):
        seg = _trend_segment(trend, i * SEGMENT_SIZE, min(n, (i + 1) * SEGMENT_SIZE))
        text = _chat_text(key, base, digest_models, _segment_prompt(game_id, i, total, seg))
        if not text:
            print(f"[ai_pick] {game_id} 走势分段 {i + 1}/{total} 失败，跳过 走势AI型")
            return None
        digests.append(f"第{i + 1}段研判：{text}")
        print(f"[ai_pick] {game_id} 走势分段 {i + 1}/{total} ok")
    rule = RULES[game_id]
    last_seg = _trend_segment(trend, n - SEGMENT_SIZE, n)
    last_text = json.dumps(last_seg, ensure_ascii=False, separators=(",", ":"))
    prompt = (
        f"你是一位在彩票店看走势图的资深彩民，擅长看走势图研判号码。"
        f"下面是{rule['label']}最近 {n} 期走势图的分段研判要点（由旧到新共 {total} 段），"
        f"以及最近一段（{SEGMENT_SIZE} 期）的原始走势图数据。\n"
        + "\n".join(digests)
        + f"\n最近一段原始走势图：{last_text}\n"
        f"请综合各段形态与最近一段的衔接，研判目标期 {target_issue}，给出 1 组号码。"
        f"不要用频率统计或遗漏排名代替看图研判。\n"
        f"出号规则：{rule['desc']}\n"
        "要求：\n"
        "1. 只输出严格 JSON，格式为 " + rule["schema"] + "，不要输出任何解释、前后缀或 markdown 代码块；\n"
        "2. JSON 中的数字必须全部符合上面的出号规则。\n"
    )
    return _call(game_id, target_issue, prompt, "走势AI型")



# ---------------------------------------------------------------------------
# AI 综合（F-综合AI型）：五家号码喂 AI 合成唯一一注（mo 2026-10-22 定版）。
# 策略退居幕后，页面只展示这一注。合成失败 → 返回 None（该期无 F，
# 展示层回退既有兜底），绝不照抄任一路冒充综合。
# ---------------------------------------------------------------------------

_METHOD_NOTES = {
    "A": "统计均衡型：频率与遗漏平衡",
    "B": "冷热组合型：热号打底、冷号点缀",
    "C": "AI智能型：AI 依据近期开奖与统计证据研判",
    "D": "评分/走势型：多维评分模型（数字彩为 AI 看近300期走势图研判）",
    "E": "走势AI型：AI 看近300期走势图研判",
}


def _pick_text(pick: dict) -> str:
    if pick.get("digits") is not None:
        return "".join(str(d) for d in pick["digits"])
    if pick.get("red") is not None:
        reds = " ".join(f"{int(n):02d}" for n in pick["red"])
        return f"红 {reds} + 蓝 {int(pick['blue']):02d}"
    front = " ".join(f"{int(n):02d}" for n in pick.get("front") or [])
    back = " ".join(f"{int(n):02d}" for n in pick.get("back") or [])
    return f"前区 {front} + 后区 {back}"


def synthesize(game_id: str, target_issue: str, picks: list[dict]) -> dict | None:
    """把各策略本期号码喂给 AI，合成唯一一注。成功返回校验后的号码 dict。"""
    usable = [p for p in (picks or []) if isinstance(p, dict) and p.get("strategy")]
    if len(usable) < 2:
        print(f"[ai_pick] {game_id} target={target_issue} synth skipped: "
              f"only {len(usable)} strategies available")
        return None
    lines = []
    for p in usable:
        label = str(p["strategy"])
        note = _METHOD_NOTES.get(label.split("-")[0].strip().upper(), "")
        lines.append(f"- {label}（{note}）：{_pick_text(p)}")
    rule = RULES[game_id]
    prompt = (
        "你是一名彩票娱乐分析合成师。下面是本期各策略 independently 给出的号码，"
        "它们的方法各不相同：\n"
        + "\n".join(lines)
        + f"\n\n请综合研判，合成唯一一注{rule['label']}号码作为本期唯一推荐："
        "权衡各路方法的可靠程度与号码之间的呼应（多路共同看好的号码权重更高），"
        "同时保持结构均衡（和值、跨度、奇偶、区间分布合理）。"
        "不要整注照抄任何一路，也不要机械多数投票，要做出独立取舍。"
        f"目标期号 {target_issue}。只输出严格 JSON，格式为 " + rule["schema"] + "，不要输出任何解释、前后缀或 markdown 代码块。"
    )
    result = _call(game_id, target_issue, prompt, "综合AI型")
    if result is not None:
        result["strategy"] = "F-综合AI型"
    else:
        print(f"[ai_pick] {game_id} target={target_issue} synth FAILED (skipped)")
    return result

def pick_trend(game_id: str, target_issue: str | None, trend: dict) -> dict | None:
    """走势AI型出号：AI 看走势图数据（src/common/trend_data 构造）直接研判出号。

    云端（OpenRouter）整段直喂；本地端点自动改走分段研判（时限原因）。
    无密钥/失败返回 None（调用方跳过该策略）。
    """
    _key, base, _models = _env_chain()
    if _key and _is_local_base(base):
        return _pick_trend_segmented(game_id, str(target_issue or "?"), trend)
    return _call(game_id, target_issue, _build_trend_prompt(game_id, str(target_issue or "?"), trend), "走势AI型")


def _call(game_id: str, target_issue: str | None, prompt: str, tag: str, local: bool = False) -> dict | None:
    if game_id not in RULES:
        print(f"[ai_pick] 未知彩种 {game_id}，跳过 {tag}")
        return None
    key, base, models = _env_chain(local)
    chan = "openrouter" if base.startswith("https://openrouter.ai") else "local"
    if not key:
        print(f"[ai_pick] 未配置 DLT_AI_API_KEY/OPENROUTER_API_KEY，跳过 {tag}（不报错）")
        return None
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://dlt.mootlsv.com/",
        "X-Title": "dlt-assistant C-AI",
        # 本地网关（Cloudflare）会拦 Python 默认 UA，必须带浏览器 UA
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    }
    url = f"{base}/chat/completions"
    for model in models:
        for attempt in (1, 2):
            try:
                body = _post_json(
                    url,
                    headers,
                    timeout=100 if chan == "local" else TIMEOUT_SECS,
                    payload={
                        "model": model,
                        "temperature": 0.2,
                        # 本地推理模型（gemma4）会先烧隐藏思考 token，300 必饿死正文
                        "max_tokens": 1200 if chan == "local" else 300,
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
                    print(f"[ai_pick] {game_id} target={target_issue} model={model} via={chan} ok")
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
    print(f"[ai_pick] {game_id} target={target_issue} 全部失败，跳过 {tag}（失败则跳过该策略）")
    return None
