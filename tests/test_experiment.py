# -*- coding: utf-8 -*-
"""实验跑批工具测试: 配置注入、权重覆盖、分段统计(合成数据, 不依赖缓存)"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from config import TRADE_CONFIG
from src.backtest.experiment import cfg_costs, default_segments, run_sweep, segment_stats
from src.strategy.multi_factor import _OverrideRegime


def _make_universe(n_stocks=32, n_days=140, seed=11):
    rng = np.random.default_rng(seed)
    data = {}
    for k in range(n_stocks):
        code = f'600{k:03d}'
        ret = rng.normal(0.0004, 0.016, n_days)
        close = 10 * np.cumprod(1 + ret)
        openc = close * (1 + rng.normal(0, 0.005, n_days))
        vol = rng.uniform(1e6, 5e6, n_days)
        data[code] = pd.DataFrame({
            'date': pd.bdate_range('2024-01-01', periods=n_days),
            'open': openc,
            'high': np.maximum(openc, close) * 1.005,
            'low': np.minimum(openc, close) * 0.995,
            'close': close, 'volume': vol, 'amount': vol * close,
            'turnover': rng.uniform(1, 5, n_days),
            'pe': rng.uniform(10, 50, n_days),
            'pb': rng.uniform(1, 5, n_days),
            'roe': rng.normal(10, 1, n_days),
            'revenue': np.abs(rng.normal(100, 4, n_days).cumsum()),
            'total_mv': rng.uniform(5e9, 5e10, n_days),
            'code': code,
        })
    index_df = pd.DataFrame({
        'date': pd.bdate_range('2024-01-01', periods=n_days),
        'open': 3000 + np.arange(n_days), 'high': 3005 + np.arange(n_days),
        'low': 2995 + np.arange(n_days), 'close': 3000 + np.arange(n_days) * 0.5,
        'volume': 1e8, 'amount': 1e10, 'pctChg': 0.5,
    })
    pool = pd.DataFrame({'code': list(data.keys()), 'name': [f'股{k}' for k in range(n_stocks)]})
    return data, index_df, pool


class TestOverrideRegime(unittest.TestCase):

    def test_override_merges_base(self):
        r = _OverrideRegime({'BULL': {'momentum_20': 0.5}})
        w = r.get_factor_weights('BULL')
        self.assertEqual(w['momentum_20'], 0.5)
        self.assertIn('ma_align_5_20_60', w)  # 其余权重保留
        # 其他状态不受影响
        self.assertNotEqual(r.get_factor_weights('BEAR').get('momentum_20'), 0.5)


class TestCostInjection(unittest.TestCase):

    def test_zero_cost_engine(self):
        from src.backtest.engine import BacktestEngine
        eng = BacktestEngine(cfg=cfg_costs(0, 0, 0))
        self.assertEqual(eng.commission, 0)
        self.assertEqual(eng.slippage, 0)
        eng2 = BacktestEngine()
        self.assertEqual(eng2.commission, TRADE_CONFIG['commission_rate'])


class TestSweep(unittest.TestCase):

    def test_sweep_runs_and_reports_all_configs(self):
        """每个配置×每段都有输出行(全变体一起报告, 不挑段)"""
        data, index_df, pool = _make_universe()
        segments = default_segments(index_df, n_segments=2)
        self.assertEqual(len(segments), 2)
        configs = [
            ('现行费用', None, None),
            ('零费用', None, cfg_costs(0, 0, 0)),
            ('动量关闭', {'BULL': {'momentum_20': 0.0}}, None),
        ]
        df = run_sweep(data, index_df, pool, configs, segments, verbose=False)
        self.assertEqual(len(df), 6)  # 3配置 × 2段
        for label in ('现行费用', '零费用', '动量关闭'):
            self.assertEqual((df['label'] == label).sum(), 2)
        # 零费用收益 ≥ 现行费用(成本只会更差, 同一信号路径下)
        for seg in ('seg1', 'seg2'):
            r_on = df[(df['label'] == '现行费用') & (df['seg'] == seg)]['ret_pct'].iloc[0]
            r_off = df[(df['label'] == '零费用') & (df['seg'] == seg)]['ret_pct'].iloc[0]
            self.assertGreaterEqual(r_off, r_on - 0.01, f"{seg} 零费用反而更差?")

    def test_segment_stats_shape(self):
        data, index_df, pool = _make_universe()
        segments = default_segments(index_df, n_segments=2)
        s, e = segments[0]
        df = run_sweep(data, index_df, pool, [('x', None, None)], [(s, e)], verbose=False)
        row = df.iloc[0]
        for col in ('ret_pct', 'max_dd_pct', 'sharpe', 'win_rate', 'n_trades'):
            self.assertIn(col, df.columns)
        self.assertTrue(np.isfinite(float(row['ret_pct'])))


if __name__ == '__main__':
    unittest.main()
