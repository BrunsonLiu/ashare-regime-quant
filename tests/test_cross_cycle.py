# -*- coding: utf-8 -*-
"""跨周期验证测试: 熊市判定、空仓减少回撤"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa

import numpy as np, pandas as pd
from src.backtest.cross_cycle import bear_mask


class TestBearMask(unittest.TestCase):

    def test_bear_in_downtrend(self):
        """均线空头+深跌 → 熊市"""
        # 横盘后45天陡跌12%(MA20<MA60且20日跌>4%)
        closes = np.concatenate([np.full(120, 3000.0), np.linspace(3000, 2640, 45)])
        c = pd.Series(closes)
        mask = bear_mask(c)
        self.assertTrue(mask.iloc[-1], "深跌末端应判为熊市")

    def test_not_bear_in_uptrend(self):
        closes = np.linspace(3000, 3600, 165)
        mask = bear_mask(pd.Series(closes))
        self.assertFalse(mask.iloc[-1], "上涨趋势不应判熊市")

    def test_warmup_is_false(self):
        """前60日(MA60未成形)不应误判"""
        mask = bear_mask(pd.Series(np.linspace(3000, 2640, 40)))
        self.assertFalse(mask.iloc[:60].any())


if __name__ == '__main__':
    unittest.main()
