# -*- coding: utf-8 -*-
"""市场结构画像测试: 游资/题材 与 机构/龙头 的区分(用户核心要求)"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa
import numpy as np, pandas as pd
from src.utils.market_structure import analyze


def _mk(n=300, trend=0.001, vol_up=2.0, vol_dn=1.0, cap=200e8, turnover=3.0):
    rng = np.random.default_rng(7)
    close = 10 * np.cumprod(1 + rng.normal(trend, 0.02, n))
    up = close[1:] > close[:-1]
    vol = np.where(up, vol_up, vol_dn) * 1e6
    vol = np.concatenate([[1e6], vol])
    return pd.DataFrame({'date': pd.bdate_range('2024-01-01', periods=n),
                         'open': close, 'high': close*1.02, 'low': close*0.98,
                         'close': close, 'volume': vol,
                         'turnover': np.full(n, turnover),
                         'outstanding_share': np.full(n, cap / close[-1])})


class TestStructure(unittest.TestCase):

    def test_small_cap_high_turnover_is_speculative(self):
        df = _mk(cap=100e8, turnover=9.0)
        r = analyze(df)
        self.assertIn('游资', r['博弈'])
        self.assertTrue(r['否决'])

    def test_large_cap_low_turnover_is_institution(self):
        df = _mk(cap=2000e8, turnover=1.5)
        r = analyze(df)
        self.assertIn('机构', r['博弈'])

    def test_divergence_smallcap_flagged_not_bigcap(self):
        # 小盘 背离行业 → 题材(否决); 个股需明显跑赢持平行业
        df = _mk(cap=200e8, trend=0.004)
        ind = pd.DataFrame({'date': df['date'], 'close': df['close'].iloc[0] * np.ones(len(df))})
        r = analyze(df, industry_df=ind)
        self.assertIn('题材', r['博弈'])
        self.assertTrue(r['否决'])
        # 大盘 同样背离 → 龙头领先(不否决)
        df2 = _mk(cap=5000e8, trend=0.004)
        ind2 = pd.DataFrame({'date': df2['date'], 'close': df2['close'].iloc[0]*np.ones(len(df2))})
        r2 = analyze(df2, industry_df=ind2)
        self.assertIn('龙头领先', r2['博弈'])
        # 大盘龙头领先不应因"题材结构"被否决(其他理由如位置/背离可独立存在)
        self.assertFalse(any('题材' in w for w in r2['理由']))

    def test_healthy_pullback_not_vetoed(self):
        df = _mk(vol_dn=0.6)   # 下跌缩量 = 健康
        r = analyze(df)
        self.assertNotIn('放量破位', r['理由'])


if __name__ == '__main__':
    unittest.main()
