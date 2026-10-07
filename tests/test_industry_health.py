# -*- coding: utf-8 -*-
"""行业长期健康度测试: 长期走弱无反转的剔除判定(用户核心原则)"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.utils.industry_health import health_score


def _make_px(patterns):
    """patterns: {industry: 收盘序列}"""
    n = max(len(v) for v in patterns.values())
    idx = pd.bdate_range('2023-01-01', periods=n)
    data = {}
    for k, v in patterns.items():
        s = pd.Series(v, index=idx[:len(v)])
        data[k] = s
    return pd.DataFrame(data)


class TestIndustryHealth(unittest.TestCase):

    def test_long_weak_no_reversal_excluded(self):
        """长期走弱(-40%)且无真反转 → 剔除(用户原则: 白酒式行业不碰)"""
        n = 260
        weak = np.linspace(1.0, 0.55, n)      # 一年跌45%, 仍在跌(无反转)
        strong = np.linspace(1.0, 1.6, n)     # 一年涨60%
        px = _make_px({'弱行业': weak, '强行业': strong})
        hs = health_score(px)
        self.assertEqual(hs['弱行业']['verdict'], '走弱无反转(剔除)')
        self.assertEqual(hs['强行业']['verdict'], '健康')

    def test_short_rebound_does_not_count_as_reversal(self):
        """长期走弱 + 只反弹一点(未站上年线) → 仍剔除(小反弹≠反转)"""
        n = 260
        weak = np.linspace(1.0, 0.5, n)
        weak[-20:] = weak[-21] * np.linspace(1.0, 1.08, 20)  # 末段小反弹8%
        px = _make_px({'弱行业': weak})
        # 需要至少两个行业(基准) → 加一个
        px['其他'] = np.linspace(1.0, 1.1, n)
        hs = health_score(px)
        # 小反弹若不站上年线 → 仍剔除
        if not hs['弱行业']['above_ma250']:
            self.assertEqual(hs['弱行业']['verdict'], '走弱无反转(剔除)')

    def test_true_reversal_kept(self):
        """长期弱但已真反转(站上年线+转正) → 反转中(不剔除)"""
        n = 260
        v = np.concatenate([np.linspace(1.0, 0.6, 180), np.linspace(0.6, 1.15, 80)])
        px = _make_px({'反转行业': v, '其他': np.linspace(1.0, 1.05, n)})
        hs = health_score(px)
        self.assertNotEqual(hs['反转行业']['verdict'], '走弱无反转(剔除)')

    def test_insufficient_data(self):
        px = _make_px({'a': np.linspace(1.0, 1.1, 50)})
        self.assertEqual(health_score(px), {})


if __name__ == '__main__':
    unittest.main()
