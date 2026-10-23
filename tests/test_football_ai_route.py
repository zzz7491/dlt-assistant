"""football_cycle AI 路由策略测试（2026-10-23 本地通道修复）。

只测 scripts/football_cycle._request_ai 的配置门与请求形状，HTTP 全 mock：
- 本地端点（所有者 Ollama）应被接受并直调 DLT_AI_MODEL（带浏览器 UA、无 provider 块）；
- 未知 base 必须走 fallback 且不发任何请求（密钥不外发）；
- OpenRouter 的 :free 路由规则保持原样。
"""
import json
import unittest
from unittest.mock import patch

from scripts import football_cycle as fc

SECTIONS = {
    "overview": "本期综合评审内容，基于市场与排名等可核验输入做取舍说明，篇幅足够通过校验。",
    "sfc_reason": "胜负彩覆盖取舍说明，分歧最大的场次采用双选，其余单选，篇幅足够通过校验。",
    "r9_reason": "任选九保留相对置信差更清晰的场次，剔除分歧过大的比赛，篇幅足够通过校验。",
    "risk": "足球赛果受临场因素影响，任何方案均不保证中奖，停售前应复核官方场次调整安排。",
}

PLAN = {"issue": "26149", "sale_end": "2026-10-26 22:00", "matches": []}
FACTS = {"schedule": "赛程事实", "factor_method": "方法事实", "factor_coverage": "覆盖事实",
         "sfc_cover": "覆盖事实", "sfc_uncertain": "不确定事实", "r9_scope": "范围事实",
         "risk": "风险事实"}


class FakeResponse:
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content": json.dumps(SECTIONS, ensure_ascii=False)}}]}


def env(**kw):
    base = {
        "DLT_AI_API_KEY": "test-key",
        "DLT_AI_BASE_URL": "https://openrouter.ai/api/v1",
        "DLT_AI_MODEL": "openrouter/free",
    }
    base.update(kw)
    return patch.dict("os.environ", base, clear=False)


class FootballAiRouteTests(unittest.TestCase):
    def setUp(self):
        self._ev = patch.object(fc, "evidence", return_value=dict(FACTS))
        self._ev.start()

    def tearDown(self):
        self._ev.stop()
    def test_local_base_calls_model_directly(self):
        with env(DLT_AI_BASE_URL="https://ai.585351.xyz/v1",
                 DLT_AI_MODEL="gemma4-26b-official:latest"):
            with patch("requests.post", return_value=FakeResponse()) as post:
                out = fc._request_ai(dict(PLAN))
        self.assertEqual(out["status"], "completed")
        args, kwargs = post.call_args
        self.assertTrue(args[0].endswith("/chat/completions"))
        self.assertEqual(kwargs["json"]["model"], "gemma4-26b-official:latest")
        self.assertNotIn("provider", kwargs["json"])
        self.assertIn("Mozilla", kwargs["headers"]["User-Agent"])
        self.assertEqual(kwargs["timeout"], 300)

    def test_unknown_base_never_calls_out(self):
        with env(DLT_AI_BASE_URL="https://evil.example/v1"):
            with patch("requests.post") as post:
                out = fc._request_ai(dict(PLAN))
        self.assertEqual(out["status"], "pending")
        post.assert_not_called()

    def test_openrouter_still_requires_free_route(self):
        with env(DLT_AI_MODEL="deepseek/deepseek-chat"):
            with patch("requests.post") as post:
                out = fc._request_ai(dict(PLAN))
        self.assertEqual(out["status"], "pending")
        post.assert_not_called()

    def test_openrouter_free_keeps_provider_block(self):
        with env():
            with patch("requests.post", return_value=FakeResponse()) as post:
                out = fc._request_ai(dict(PLAN))
        self.assertEqual(out["status"], "completed")
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"].get("provider"), {"require_parameters": True})


if __name__ == "__main__":
    unittest.main()
