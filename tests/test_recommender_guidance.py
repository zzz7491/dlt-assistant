"""F 合成注入上期复盘改进（反思闭环消费端）与 guidance 提示词测试。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import recommender
from src.common import ai_pick


class GuidanceTests(unittest.TestCase):
    def _write_cycle(self, payload):
        tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
        json.dump(payload, tmp, ensure_ascii=False)
        tmp.close()
        return Path(tmp.name)

    def test_loader_reads_latest_improvement(self):
        path = self._write_cycle({'review': {'status': 'completed', 'issue': '26120',
            'reflection': {'improvement': {'text': '和值向中部收敛，补足第三区覆盖。'}}}})
        self.assertEqual(recommender._latest_review_improvement('26121', _path=path),
                         '和值向中部收敛，补足第三区覆盖。')
        # 复盘期号不早于目标期 → 不注入
        self.assertIsNone(recommender._latest_review_improvement('26120', _path=path))

    def test_loader_fail_open_on_garbage(self):
        path = self._write_cycle({'review': None})
        self.assertIsNone(recommender._latest_review_improvement('26121', _path=path))
        self.assertIsNone(recommender._latest_review_improvement('26121', _path=Path('/nonexistent/x.json')))

    def test_synthesize_prompt_carries_guidance(self):
        seen = {}

        def fake_call(game_id, target_issue, prompt, label):
            seen['prompt'] = prompt
            return {'front': [1, 2, 3, 4, 5], 'back': [1, 2]}

        picks = [{'strategy': 'A-均衡统计型', 'front': [1, 2, 3, 4, 5], 'back': [1, 2]},
                 {'strategy': 'B-冷热组合型', 'front': [6, 7, 8, 9, 10], 'back': [3, 4]}]
        with patch.object(ai_pick, '_call', fake_call):
            out = ai_pick.synthesize('dlt', '26121', picks, guidance='和值向中部收敛。')
        self.assertIsNotNone(out)
        self.assertIn('上期复盘立下的改进要求', seen['prompt'])
        self.assertIn('和值向中部收敛。', seen['prompt'])
        with patch.object(ai_pick, '_call', fake_call):
            ai_pick.synthesize('dlt', '26121', picks)
        self.assertNotIn('上期复盘立下的改进要求', seen['prompt'])


if __name__ == '__main__':
    unittest.main()
