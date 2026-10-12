# -*- coding: utf-8 -*-
"""data_loader.get_us_index 涨跌幅兜底回归测试(全 mock, 不出网)

历史 bug: 新版 akshare index_global_hist_em 返回"涨跌幅"列但值为 NaN →
代码只在"无该列"时才从收盘价补算 → 末行 pct_chg 为 NaN → overseas 页涨跌幅显示 '--'。
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import pandas as pd


class TestUsIndexPctChg(unittest.TestCase):
    def _loader(self):
        from src.data_loader import DataLoader
        return DataLoader()

    def _fake_ak(self, df):
        """返回一个 patch 目标: 让 ak.index_global_hist_em 返回给定 df。"""
        import src.data_loader as dl
        return patch.object(dl.ak, 'index_global_hist_em', return_value=df)

    def test_pct_chg_computed_when_column_missing(self):
        df = pd.DataFrame({'日期': pd.bdate_range('2026-01-01', periods=3),
                           '收盘': [100.0, 110.0, 121.0]})
        with self._fake_ak(df):
            r = self._loader().get_us_index('标普500')
        self.assertIn('pct_chg', r.columns)
        self.assertAlmostEqual(r['pct_chg'].iloc[-1], 10.0, places=2)

    def test_pct_chg_computed_when_column_all_nan(self):
        """实测场景: 有'涨跌幅'列但值全 NaN → 必须补算(旧代码漏此分支)。"""
        df = pd.DataFrame({'日期': pd.bdate_range('2026-01-01', periods=3),
                           '最新价': [100.0, 110.0, 121.0],
                           '涨跌幅': [float('nan')] * 3})
        with self._fake_ak(df):
            r = self._loader().get_us_index('标普500')
        self.assertIsNotNone(r['pct_chg'].iloc[-1])
        self.assertFalse(pd.isna(r['pct_chg'].iloc[-1]), '末行涨跌幅仍为 NaN')
        self.assertAlmostEqual(r['pct_chg'].iloc[-1], 10.0, places=2)

    def test_existing_pct_chg_preserved(self):
        """接口已给出有效涨跌幅 → 不应被覆盖。"""
        df = pd.DataFrame({'日期': pd.bdate_range('2026-01-01', periods=3),
                           '收盘': [100.0, 110.0, 121.0],
                           '涨跌幅': [0.0, 10.0, 9.99]})
        with self._fake_ak(df):
            r = self._loader().get_us_index('标普500')
        self.assertAlmostEqual(r['pct_chg'].iloc[-1], 9.99, places=2)

    def test_returns_none_on_error(self):
        import src.data_loader as dl
        with patch.object(dl.ak, 'index_global_hist_em', side_effect=RuntimeError('boom')):
            self.assertIsNone(self._loader().get_us_index('标普500'))


if __name__ == '__main__':
    unittest.main()
