# -*- coding: utf-8 -*-
"""决策树测试: 炸板率修正只降温不升温(冰点日绝不升仓)、notes 不重复"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import pandas as pd

from src.sentiment.decision_tree import TradingDecisionTree


def _sentiment(score, heat, zhaban=0.2, zt=60):
    return {'date': '20260731', 'zt_count': zt, 'zhaban_count': 10, 'zhaban_rate': zhaban,
            'lianban_height': 3, 'strong_zt_count': 5, 'north_net': 0, 'north_3d': 0,
            'lhb_net': 0, 'sentiment_score': score, 'heat_level': heat}


class TestZhabanCooling(unittest.TestCase):
    """核心回归: 修复前炸板率>35%会把 COLD 升成 WARM + max(0,·)反向钳位"""

    def setUp(self):
        self.tree = TradingDecisionTree()

    def test_cold_day_stays_cold_under_high_zhaban(self):
        """冰点日( score=-2 ) + 高炸板率 → 仍是 COLD 0仓, 分数继续下探"""
        with patch.object(self.tree.collector, 'calc_sentiment_indicators',
                          return_value=_sentiment(-2, 'COLD', zhaban=0.4, zt=25)):
            ctx = self.tree.assess_market('20260731')
        self.assertEqual(ctx.sentiment['heat_level'], 'COLD')
        self.assertEqual(ctx.sentiment['sentiment_score'], -3)
        self.assertEqual(ctx.max_positions, 0)

    def test_extreme_zhaban_caps_score_at_minus_one(self):
        """炸板率>50% → 等级不高于 CHILLY, 分数封顶 -1"""
        with patch.object(self.tree.collector, 'calc_sentiment_indicators',
                          return_value=_sentiment(3.0, 'HOT', zhaban=0.6, zt=120)):
            ctx = self.tree.assess_market('20260731')
        self.assertEqual(ctx.sentiment['heat_level'], 'CHILLY')
        self.assertLessEqual(ctx.sentiment['sentiment_score'], -1)

    def test_hot_day_cools_one_level(self):
        """HOT + 炸板率0.4 → 降一档到 WARM, 分数扣1"""
        with patch.object(self.tree.collector, 'calc_sentiment_indicators',
                          return_value=_sentiment(2.0, 'HOT', zhaban=0.4, zt=100)):
            ctx = self.tree.assess_market('20260731')
        self.assertEqual(ctx.sentiment['heat_level'], 'WARM')
        self.assertEqual(ctx.sentiment['sentiment_score'], 1.0)

    def test_cooling_never_warms(self):
        """任何炸板率修正都不能把 colder 等级抬热"""
        for score, heat in [(-0.5, 'CHILLY'), (-2, 'COLD')]:
            with patch.object(self.tree.collector, 'calc_sentiment_indicators',
                              return_value=_sentiment(score, heat, zhaban=0.4)):
                ctx = self.tree.assess_market('20260731')
            rank = {'COLD': 0, 'CHILLY': 1, 'WARM': 2, 'HOT': 3}
            self.assertLessEqual(rank[ctx.sentiment['heat_level']], rank[heat])

    def test_downtrend_bias_cools(self):
        """三日连降情绪 → 扣1分, 等级不高于WARM"""
        hist = pd.DataFrame({'sentiment_score': [1.0, 0.0, -0.5]})
        with patch.object(self.tree.collector, 'calc_sentiment_indicators',
                          return_value=_sentiment(2.0, 'HOT', zhaban=0.2)):
            ctx = self.tree.assess_market('20260731', sentiment_history=hist)
        self.assertEqual(ctx.sentiment['heat_level'], 'WARM')
        self.assertEqual(ctx.sentiment['sentiment_score'], 1.0)


class TestNotes(unittest.TestCase):

    def test_notes_not_duplicated(self):
        """make_decision 返回的 notes 中前置条目不得出现2-3次"""
        tree = TradingDecisionTree()
        with patch.object(tree.collector, 'calc_sentiment_indicators',
                          return_value=_sentiment(2.0, 'HOT', zhaban=0.1, zt=100)):
            with patch.object(tree.collector, 'get_limit_up_pool', return_value=pd.DataFrame()):
                result = tree.make_decision(
                    date='20260731', positions={}, capital=100000, total_value=100000,
                    daily_data={}, sentiment_history=None, pool=None, blocked=False)
        notes = result['notes']
        for n in notes:
            self.assertEqual(notes.count(n), 1, f"notes重复: {n}")


if __name__ == '__main__':
    unittest.main()
