# -*- coding: utf-8 -*-
"""情绪择时回测测试: 反前视纪律(扩展分位不偷看/T+1开盘成交)"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.backtest import sentiment_timing as st


def _make_df(n=200, ice_every=10):
    """合成数据: 每 ice_every 天制造一个冰点日(涨停数骤降), 价格缓涨"""
    dates = pd.bdate_range('2024-01-01', periods=n)
    close = 3000 + np.arange(n) * 2.0
    open_ = close - 1.0
    zt = np.full(n, 60.0)
    zt[::ice_every] = 10.0            # 冰点: 涨停数骤降
    zr = np.full(n, 0.2)
    return pd.DataFrame({
        'date': dates, 'open': open_, 'close': close,
        'zt_count': zt, 'zhaban_rate': zr,
    })


class TestExpandingThresholds(unittest.TestCase):

    def test_thresholds_do_not_peek(self):
        """扩展分位数: 第t行阈值必须等于[0..t]的分位数(不许用未来数据)"""
        df = st.expanding_thresholds(_make_df())
        raw = df[['zt_count', 'zhaban_rate']]
        t = 150
        expected_p20 = np.quantile(raw['zt_count'].values[:t + 1], 0.20)
        self.assertEqual(df['p20_zt'].iloc[t], expected_p20)
        # 预热期为 NaN(不出信号)
        self.assertTrue(np.isnan(df['p20_zt'].iloc[:st.WARMUP]).all())
        # 预热期无信号
        self.assertEqual(df['is_ice'].iloc[:st.WARMUP].sum(), 0)

    def test_ice_flag_matches_definition(self):
        df = st.expanding_thresholds(_make_df())
        t = 150
        should_ice = (df['zt_count'].iloc[t] < df['p20_zt'].iloc[t]) or \
                     (df['zhaban_rate'].iloc[t] > df['p80_zr'].iloc[t])
        self.assertEqual(int(should_ice), df['is_ice'].iloc[t])


class TestFixedHoldNoLookahead(unittest.TestCase):

    def test_entry_is_next_open_with_slippage(self):
        """T日冰点信号 → T+1开盘买入(含滑点), 绝不用T日价格"""
        df = st.expanding_thresholds(_make_df(ice_every=10))
        trades = st.run_fixed_hold(df, hold_days=3)
        self.assertTrue(trades)
        opens = dict(zip(df['date'], df['open']))
        for t in trades:
            expected_entry = opens[t['entry_date']] * (1 + st.SLIPPAGE)
            # 反查: entry_date 必须是信号日的下一个交易日
            sig_idx = df.index[df['date'] == t['signal_date']][0]
            self.assertEqual(df['date'].iloc[sig_idx + 1], t['entry_date'])
            self.assertAlmostEqual(
                t['ret'],
                (opens[t['exit_date']] * (1 - st.SLIPPAGE) / expected_entry
                 - 1 - st.COST_ROUNDTRIP), places=10)

    def test_no_overlapping_positions(self):
        """持仓期间忽略新信号(一笔未平不叠新仓)"""
        df = st.expanding_thresholds(_make_df(ice_every=3))
        trades = st.run_fixed_hold(df, hold_days=10)
        spans = sorted((t['entry_date'], t['exit_date']) for t in trades)
        for (_, prev_exit), (next_entry, _) in zip(spans, spans[1:]):
            self.assertLess(prev_exit, next_entry, "出现重叠持仓")

    def test_recovery_exit_within_max_hold(self):
        """修复退出: 持有期不超过 max_hold"""
        df = st.expanding_thresholds(_make_df(ice_every=10))
        trades = st.run_recovery_exit(df, max_hold=5)
        dates = df['date'].tolist()
        for t in trades:
            hold = dates.index(t['exit_date']) - dates.index(t['entry_date'])
            self.assertLessEqual(hold, 5, "修复退出超过最大持有期")


if __name__ == '__main__':
    unittest.main()
