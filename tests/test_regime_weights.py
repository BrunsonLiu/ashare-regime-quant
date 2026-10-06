# -*- coding: utf-8 -*-
"""Regime IC权重测试: 权重估计的归一化与噪声剔除、按状态整表替换"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.strategy.multi_factor import _OverrideRegime
from src.backtest.regime_weights import IC_MIN, compute_ic_weights


class TestRegimeTables(unittest.TestCase):

    def test_regime_tables_replace_by_state(self):
        """_regime_tables 按状态整表替换, 未列出的状态回退基础表"""
        tables = {'SHOCK': {'momentum_20': 1.0, 'reversal_5': -0.5}}
        r = _OverrideRegime({'_regime_tables': tables})
        shock = r.get_factor_weights('SHOCK')
        self.assertEqual(set(shock.keys()), {'momentum_20', 'reversal_5'})
        self.assertEqual(shock['momentum_20'], 1.0)
        # BEAR 未在tables中 → 回退基础表(含默认因子)
        bear = r.get_factor_weights('BEAR')
        self.assertIn('reversal_5', bear)
        self.assertNotEqual(set(bear.keys()), {'momentum_20', 'reversal_5'})

    def test_empty_regime_table_falls_back(self):
        """空表状态回退基础表(不能返回空权重导致全0信号)"""
        r = _OverrideRegime({'_regime_tables': {'BULL': {}, 'SHOCK': {'momentum_20': 1.0}}})
        bull = r.get_factor_weights('BULL')
        self.assertTrue(len(bull) > 0, "空表应回退基础表而非返回空")


class TestICWeights(unittest.TestCase):

    def _panels_and_fwd(self, n=80, days=120):
        rng = np.random.default_rng(5)
        dates = pd.bdate_range('2024-01-01', periods=days)
        panels, fwd = {}, {}
        for k in range(40):
            code = f'600{k:03d}'
            # 因子值随机, 前向收益与因子有弱相关(制造IC)
            fval = rng.normal(0, 1, days)
            panels[code] = {'dates': dates.values, 'factors': {'momentum_20': fval}}
            fwd[code] = {dates[i]: 0.3 * fval[i] + rng.normal(0, 1)
                         for i in range(days - 10)}
        return panels, fwd

    def test_weights_normalized_and_noise_dropped(self):
        panels, fwd = self._panels_and_fwd()
        reg_map = {d: 'SHOCK' for d in pd.bdate_range('2024-01-01', periods=120)}
        train_dates = pd.bdate_range('2024-01-01', periods=120)
        weights, meta = compute_ic_weights(panels, fwd, reg_map, ['momentum_20'], train_dates)
        w = weights.get('SHOCK', {})
        if w:  # 若估计出权重
            self.assertLessEqual(abs(sum(abs(v) for v in w.values())), 1.001)
            for v in w.values():
                self.assertGreaterEqual(abs(v), IC_MIN - 1e-9,
                                        "低于阈值的噪声因子不应保留")
        # meta 结构
        self.assertIn('ic_matrix', meta)


if __name__ == '__main__':
    unittest.main()
