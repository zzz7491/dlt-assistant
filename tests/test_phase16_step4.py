# -*- coding: utf-8 -*-
"""
Phase 16 Step 4 展示层测试。

覆盖：
- 所有 public/data/*.json 正常（存在 + 解析 + 关键字段）
- experiment.html 含全部章节 id 与诚实文案；不出现「自动调权已启用」错误状态
- experiment.js 语法正确（node --check）
- Node DOM 桩：所有 JSON 正常加载 / 某份 JSON 缺失时 fallback 正常
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public")
DATA = os.path.join(PUBLIC, "data")
HTML = os.path.join(PUBLIC, "experiment.html")
JS = os.path.join(PUBLIC, "experiment.js")


def _node():
    managed = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2\node.exe"
    if os.path.exists(managed):
        return managed
    found = shutil.which("node")
    if found:
        return found
    pytest.skip("node 不可用，跳过 DOM 桩测试")


# ---------- 1. 数据 JSON ----------
EXPECTED_KEYS = {
    "model_ranking.json": ["models", "ranking", "beats_random"],
    "phase15_model_diagnostics.json": ["models", "conclusion"],
    "phase15_feature_gain.json": ["feature_importance", "models"],
    "phase15_reward_stability.json": ["models"],
    "phase15_counterfactual.json": ["feature_ablation", "strategy_removal", "ensemble_comparison", "overall_conclusion"],
    "phase16_entertainment.json": ["models", "ranking", "vs_random"],
    "phase16_step3_validation.json": ["config", "validity", "aggregate", "stability_verdict", "combos"],
}


@pytest.mark.parametrize("fname,keys", list(EXPECTED_KEYS.items()))
def test_display_data_files(fname, keys):
    p = os.path.join(DATA, fname)
    assert os.path.exists(p), f"缺失展示数据文件 {fname}"
    with open(p, "r", encoding="utf-8") as fh:
        obj = json.load(fh)  # 必须可解析
    for k in keys:
        assert k in obj, f"{fname} 缺少关键字段 {k}"


def test_step3_validity_marker_present():
    with open(os.path.join(DATA, "phase16_step3_validation.json"), encoding="utf-8") as fh:
        obj = json.load(fh)
    assert obj["stability_verdict"]["coverage_boost_stable"] is False
    assert obj["validity"]["affects_step3_results"] is False
    assert "caveat" in obj["validity"]


# ---------- 2. HTML 结构 + 诚实文案 ----------
def _html_text():
    with open(HTML, encoding="utf-8") as fh:
        return fh.read()


def test_html_sections_present():
    html = _html_text()
    for sid in [
        "sec-overview", "sec-live", "sec-overview-models", "sec-ranking",
        "sec-diagnostics", "sec-entertainment", "sec-counterfactual",
        "sec-stability", "sec-no-autotune", "sec-method",
    ]:
        assert f'id="{sid}"' in html, f"缺少章节容器 {sid}"
    # 容器 id（JS 渲染目标）
    for cid in [
        "model-overview", "model-diagnostics", "reward-stability",
        "entertainment", "counterfactual", "stability", "why-no-autotune",
    ]:
        assert f'id="{cid}"' in html, f"缺少渲染容器 {cid}"


def test_html_honest_strings_and_no_false_status():
    html = _html_text()
    assert "随机基准" in html
    assert "coverage_boost" in html  # 稳定性章节静态文案已点名
    assert "自动调权" in html  # 出现「为什么没有自动调权」章节语境
    assert "自动调权已启用" not in html, "页面不得出现『自动调权已启用』错误状态"
    # 注：「不稳定」「未启用自动调权」等动态文案由 experiment.js 渲染，由 DOM 桩测试验证


def test_js_syntax_ok():
    node = _node()
    r = subprocess.run([node, "--check", JS], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"experiment.js 语法检查失败: {r.stderr}"


# ---------- 3. DOM 桩：真实加载 ----------
def _run_dom(fail_file=None):
    node = _node()
    env = dict(os.environ)
    if fail_file:
        env["FAIL_FILE"] = fail_file
    return subprocess.run([node, os.path.join(ROOT, "tests", "_page_step4_dom.cjs")],
                          cwd=ROOT, capture_output=True, text=True, env=env)


def test_dom_all_json_ok():
    r = _run_dom()
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
    assert r.returncode == 0, "所有 JSON 正常时 DOM 断言失败"


def test_dom_missing_one_json_fallback():
    r = _run_dom(fail_file="phase16_step3_validation.json")
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
    assert r.returncode == 0, "某份 JSON 缺失时 fallback 断言失败"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-p", "no:cacheprovider"]))
