# -*- coding: utf-8 -*-
"""市场状态判断测试: 120日窗口守卫、配置阈值、权重表完整性"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from config import REGIME_CONFIG
from src.utils.market_regime import MarketRegime


def _index(closes):
    n = len(closes)
    return pd.DataFrame({
        'date': pd.bdate_range('2025-01-01', periods=n),
        'open': closes, 'high': closes * 1.01, 'low': closes * 0.99,
        'close': closes, 'volume': 1e8, 'amount': 1e10, 'pctChg': 0.5,
    })


class TestDetect(unittest.TestCase):

    def setUp(self):
        self.regime = MarketRegime()

    def _bear_curve(self, n):
        """构造满足熊市判定的曲线: 横盘后45天陡跌12%(MA死叉+近20日跌超4%+低波动)"""
        flat = n - 45
        top = 3000.0 if n <= 100 else 3100.0
        closes = np.concatenate([np.full(flat, top),
                                 np.linspace(top, top * 0.88, 45)])
        return _index(closes)

    def test_short_history_no_crash_and_no_slow_bull(self):
        """60~119日数据: 不崩溃, 慢牛维度显式停用(修复前 rolling(120) 静默 NaN)"""
        n = 80
        state = self.regime.detect(_index(np.linspace(3000, 3100, n)))
        self.assertIn(state['regime'], ('BULL', 'SHOCK', 'BEAR'))
        self.assertEqual(state['slow_bull_score'], 0)

    def test_short_history_bear_still_detected(self):
        """数据不足120日时熊市趋势确认仍生效(死叉+阴跌)"""
        state = self.regime.detect(self._bear_curve(70))
        self.assertEqual(state['regime'], 'BEAR')

    def test_downtrend_long_history_is_bear(self):
        state = self.regime.detect(self._bear_curve(150))
        self.assertEqual(state['regime'], 'BEAR')

    def test_uptrend_long_history_scores_positive(self):
        n = 150
        closes = np.concatenate([np.full(80, 3000.0), np.linspace(3000, 3400, 70)])
        state = self.regime.detect(_index(closes))
        self.assertGreater(state['bull_score'], state['bear_score'])

    def test_vol_thresholds_from_config(self):
        """波动率阈值读配置(修复前硬编码, 改配置不生效)"""
        self.assertEqual(self.regime.bull_vol, REGIME_CONFIG['bull_vol_threshold'])
        self.assertEqual(self.regime.bear_vol, REGIME_CONFIG['bear_vol_threshold'])

    def test_output_values_finite(self):
        df = _index(np.linspace(3000, 3060, 130))
        state = self.regime.detect(df)
        for key in ('ma_short', 'ma_long', 'volatility', 'trend_strength', 'recent_return'):
            self.assertTrue(np.isfinite(state[key]), f"{key} 不是有限数值")


class TestWeights(unittest.TestCase):

    def setUp(self):
        self.regime = MarketRegime()

    def test_no_dead_placeholder_weights(self):
        """north_flow_5(恒0占位)不得再出现在任何权重表"""
        for regime in ('BULL', 'BEAR', 'SHOCK'):
            weights = self.regime.get_factor_weights(regime)
            self.assertNotIn('north_flow_5', weights, f"{regime} 权重表仍含死因子")

    def test_weights_reference_registered_factors(self):
        """权重表中的因子都应在策略注册表中存在"""
        from src.strategy.multi_factor import MultiFactorStrategy
        strategy = MultiFactorStrategy()
        for regime in ('BULL', 'BEAR', 'SHOCK'):
            for fname in self.regime.get_factor_weights(regime):
                self.assertIn(fname, strategy.engine.factors,
                              f"{regime} 权重表引用了未注册因子 {fname}")

    def test_position_advice_for_all_regimes(self):
        for regime in ('BULL', 'SHOCK', 'BEAR', 'UNKNOWN'):
            advice = self.regime.get_position_advice(regime)
            self.assertIn('max_position_pct', advice)
            self.assertIn('max_holdings', advice)


if __name__ == '__main__':
    unittest.main()
