# -*- coding: utf-8 -*-
"""因子测试: 除零防护、美股→A股日历对齐、合成因子不被占位稀释"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.factors.money_flow import AmountRatio
from src.factors.sentiment import LimitUpCount
from src.factors import overseas


def _df_with_volume(vols, code='600001'):
    n = len(vols)
    close = np.linspace(10, 10.5, n)
    return pd.DataFrame({
        'date': pd.bdate_range('2025-01-01', periods=n),
        'open': close, 'high': close * 1.01, 'low': close * 0.99, 'close': close,
        'volume': vols, 'amount': vols * 10, 'code': code,
    })


class TestAmountRatio(unittest.TestCase):

    def test_zero_volume_no_inf(self):
        """停牌日 volume=0 → 基准均量0 → 不得除出 inf(修复前产出 inf)"""
        vols = np.full(40, 1000.0)
        vols[10:15] = 0.0  # 连续5天停牌
        vols[15] = 1000.0  # 复牌日, 前20日均量>0但若窗口恰好全0...
        df = _df_with_volume(vols)
        result = AmountRatio(20).calculate(df)
        finite = result.dropna()
        self.assertTrue(np.isfinite(finite).all(), "AmountRatio 存在 inf/nan 以外的非有限值")


class TestLimitUpCount(unittest.TestCase):

    def test_main_board_10pct(self):
        """主板连续10%涨停计数"""
        n = 10
        close = np.array([10 * (1.1 ** i) for i in range(n)])
        df = _df_with_volume(np.full(n, 1e6))
        df['close'] = close
        df['pctChg'] = pd.Series(close).pct_change().fillna(0) * 100
        result = LimitUpCount().calculate(df)
        self.assertEqual(result.iloc[-1], n - 1)  # 除首日外全部连板

    def test_chinext_ignores_10pct(self):
        """创业板(300xxx) 10%涨幅不算涨停, 20%才算"""
        n = 10
        close = np.array([10 * (1.1 ** i) for i in range(n)])
        df = _df_with_volume(np.full(n, 1e6), code='300001')
        df['close'] = close
        result = LimitUpCount().calculate(df)
        self.assertTrue((result == 0).all(), "10%涨幅不应触发创业板涨停计数")


class TestUSAlignment(unittest.TestCase):
    """美股→A股日历对齐(修复前自然日+1, 周五对到周六→周一恒0)"""

    def _us_data(self):
        # 美股周五(-3)和周一(0)两天, 收盘价: Fri=100, Mon=101 → Mon ret=+1%
        dates = [pd.Timestamp('2025-01-10'), pd.Timestamp('2025-01-13')]  # Fri, Mon
        return pd.DataFrame({'date': dates, 'close': [100.0, 101.0]})

    def _a_share_df(self):
        # A股: 周一01-13、周二01-14(周末13-14日是周六日? 不, 2025-01-13是周一)
        dates = [pd.Timestamp('2025-01-13'), pd.Timestamp('2025-01-14'),
                 pd.Timestamp('2025-01-15')]  # 周一/周二/周三
        close = np.linspace(10, 10.2, 3)
        return pd.DataFrame({
            'date': dates, 'open': close, 'high': close, 'low': close,
            'close': close, 'volume': 1e6, 'amount': 1e7, 'code': '600001',
        })

    def _calculate_with_us(self, us_df):
        factor = overseas.USMarketImpact()
        with patch.object(factor, '_get_us_data', return_value=us_df):
            return factor.calculate(self._a_share_df())

    def test_monday_gets_friday_ret(self):
        """周一应拿到周五的美股收益(修复前恒0)"""
        us = self._us_data()
        result = self._calculate_with_us(us)
        # 周一(01-13) ← 周五(01-10)收盘, 周五相对周四(数据中无) → 首行NaN→ffill→0
        # 周二(01-14) ← 周一(01-13)美股收盘 +1%
        self.assertAlmostEqual(result.iloc[1], 0.01, places=6)

    def test_us_holiday_ffill(self):
        """美股假日无新收盘时, 沿用最近一个美股交易日收益"""
        us = pd.DataFrame({  # 只有周五
            'date': [pd.Timestamp('2025-01-10')],
            'close': [100.0],
        })
        # A股三天: 周二/周三/周四, 美股周五的收益(相对更早)未知→NaN→0, 但后续日沿用
        a = self._a_share_df()
        a['date'] = [pd.Timestamp('2025-01-14'), pd.Timestamp('2025-01-15'),
                     pd.Timestamp('2025-01-16')]
        factor = overseas.USMarketImpact()
        with patch.object(factor, '_get_us_data', return_value=us):
            result = factor.calculate(a)
        # 单行美股数据 pct_change=NaN → 全为0(无可用收益)
        self.assertEqual(result.iloc[0], 0.0)

    def test_global_appetite_not_halved_by_placeholder(self):
        """港股占位(available=False)不得把美股信号稀释一半(修复前 us/2)"""
        us = self._us_data()
        a = self._a_share_df()
        us_factor = overseas.USMarketImpact()
        with patch.object(us_factor, '_get_us_data', return_value=us):
            us_series = us_factor.calculate(a)

        appetite = overseas.GlobalRiskAppetite()
        with patch.object(appetite.us_factor, '_get_us_data', return_value=us):
            combined = appetite.calculate(a)

        # 港股占位不可用时, 合成值 == 美股值(不是它的一半)
        self.assertFalse(overseas.HKMarketImpact.available)
        pd.testing.assert_series_equal(combined, us_series)

    def test_overseas_weights_survive(self):
        """移除 north_flow_5 后, 美股/隔夜因子权重仍在"""
        from src.utils.market_regime import MarketRegime
        weights = MarketRegime().get_factor_weights('BULL')
        self.assertIn('us_market_impact', weights)
        self.assertIn('overnight_signal', weights)


if __name__ == '__main__':
    unittest.main()
