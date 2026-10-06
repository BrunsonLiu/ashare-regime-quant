# -*- coding: utf-8 -*-
"""Regime 条件IC测试: 状态判定、前向收益时序契约、IC符号"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.backtest import regime_ic as ri


class TestRegimeSeries(unittest.TestCase):

    def test_bull_bear_shock_labels(self):
        n = 140
        # 前段横盘(SHOCK), 后段陡涨(BULL)
        closes = np.concatenate([np.full(70, 3000.0), np.linspace(3000, 3600, 70)])
        idx = pd.DataFrame({'date': pd.bdate_range('2024-01-01', periods=n),
                            'close': closes, 'open': closes, 'high': closes * 1.01,
                            'low': closes * 0.99, 'volume': 1e8, 'amount': 1e10})
        rs = ri.regime_series(idx)
        vals = [v for _, v in sorted(rs.items()) if v != 'WARMUP']
        self.assertIn('BULL', vals)
        self.assertEqual(vals[0], 'SHOCK')  # 前段横盘

    def test_warmup_before_ma_long(self):
        n = 140
        dates = pd.bdate_range('2024-01-01', periods=n)
        idx = pd.DataFrame({'date': dates,
                            'close': np.linspace(3000, 3200, n),
                            'open': np.linspace(3000, 3200, n),
                            'high': np.linspace(3000, 3200, n) * 1.01,
                            'low': np.linspace(3000, 3200, n) * 0.99,
                            'volume': 1e8, 'amount': 1e10})
        rs = ri.regime_series(idx)
        # MA60 需要 60 个值, 前 60 个交易日(index 0..59)必须是 WARMUP
        for i in range(59):
            self.assertEqual(rs[dates[i]], 'WARMUP', f'第{i}个交易日应为WARMUP')
        # index 60 起应有明确状态
        self.assertIn(rs[dates[60]], ('BULL', 'SHOCK', 'BEAR'))


class TestForwardReturns(unittest.TestCase):

    def test_open_to_open_contract(self):
        """前向收益 = T+1开盘 → T+1+N开盘(与回测同一时序契约, 无前视)"""
        df = pd.DataFrame({
            'date': pd.bdate_range('2024-01-01', periods=20),
            'open': np.arange(20, dtype=float) + 100,   # 100,101,...
            'high': 200.0, 'low': 50.0, 'close': 150.0,
            'volume': 1e6, 'amount': 1e7,
        })
        fwd = ri.forward_returns({'600001': df}, horizon=5)
        m = fwd['600001']
        # T=第5行(index5, open=105) → 买入T+1(open=106), 卖出T+6(open=111)
        T = pd.bdate_range('2024-01-01', periods=20)[5]
        self.assertIn(T, m)
        self.assertAlmostEqual(m[T], 111 / 106 - 1, places=10)

    def test_no_entry_near_end(self):
        df = pd.DataFrame({
            'date': pd.bdate_range('2024-01-01', periods=10),
            'open': np.arange(10, dtype=float) + 100,
            'high': 200.0, 'low': 50.0, 'close': 150.0,
            'volume': 1e6, 'amount': 1e7,
        })
        fwd = ri.forward_returns({'600001': df}, horizon=5)
        dates = pd.bdate_range('2024-01-01', periods=10)
        # 末尾无法完成 T+1+5, 不应有收益记录
        self.assertNotIn(dates[-1], fwd['600001'])
        self.assertNotIn(dates[-3], fwd['600001'])


class TestPersistence(unittest.TestCase):

    def test_runs_counted(self):
        dates = pd.bdate_range('2024-01-01', periods=10)
        reg = {d: v for d, v in zip(dates, ['SHOCK'] * 4 + ['BEAR'] * 3 + ['BULL'] * 3)}
        p = ri.regime_persistence(reg)
        self.assertEqual(p['SHOCK']['段数'], 1)
        self.assertEqual(p['SHOCK']['平均天数'], 4)
        self.assertEqual(p['BULL']['平均天数'], 3)


if __name__ == '__main__':
    unittest.main()
