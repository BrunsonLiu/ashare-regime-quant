# -*- coding: utf-8 -*-
"""direct_data 测试: 指数 secid 市场前缀、涨跌停池解析(全部走 mock, 不出网)"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import pandas as pd

from src.direct_data import DirectDataFetcher


class _CaptureFetcher(DirectDataFetcher):
    """替换 _fetch: 记录请求URL, 返回预置响应"""

    def __init__(self, response):
        super().__init__()
        self.response = response
        self.urls = []

    def _fetch(self, url, timeout=10, retries=3):
        self.urls.append(url)
        return self.response


class TestIndexSecid(unittest.TestCase):
    """修复回归: 399xxx(深市)必须用 secid=0., 000xxx(沪市)用 secid=1."""

    def test_sz_index_uses_market_0(self):
        resp = {'data': {'f58': '深证成指', 'f43': 1000000, 'f170': 120, 'f169': 12000}}
        f = _CaptureFetcher(resp)
        df = f.get_index_realtime(['399001'])
        self.assertIn('secid=0.399001', f.urls[0])
        self.assertEqual(len(df), 1)

    def test_sh_index_uses_market_1(self):
        resp = {'data': {'f58': '上证指数', 'f43': 380080, 'f170': -50, 'f169': -1900}}
        f = _CaptureFetcher(resp)
        df = f.get_index_realtime(['000001'])
        self.assertIn('secid=1.000001', f.urls[0])
        self.assertEqual(len(df), 1)

    def test_field_mapping_stock_get(self):
        """锁死字段映射: stock/get 用 f43家族, 且价格/涨跌幅 ÷100。
        (旧代码误用 clist 的 f2/f3/f4 → 真实接口下为空 → close 全 null)"""
        resp = {'data': {'f58': '上证指数', 'f43': 380080, 'f44': 382822,
                         'f45': 379517, 'f46': 379876, 'f47': 123456,
                         'f48': 5.6e11, 'f60': 381270,
                         'f169': -1190, 'f170': -31}}
        f = _CaptureFetcher(resp)
        row = f.get_index_realtime(['000001']).iloc[0]
        self.assertAlmostEqual(row['close'], 3800.80, places=2)
        self.assertAlmostEqual(row['high'], 3828.22, places=2)
        self.assertAlmostEqual(row['low'], 3795.17, places=2)
        self.assertAlmostEqual(row['open'], 3798.76, places=2)
        self.assertAlmostEqual(row['pre_close'], 3812.70, places=2)
        self.assertAlmostEqual(row['chg'], -11.90, places=2)
        self.assertAlmostEqual(row['chg_pct'], -0.31, places=2)
        self.assertEqual(row['volume'], 123456)
        # 请求必须含 stock/get 的字段号, 不含 clist 的 f2
        self.assertIn('f43', f.urls[0])
        self.assertIn('f170', f.urls[0])
        self.assertNotIn('=f2,', f.urls[0].replace('fields=', 'fields='))  # 不应请求裸 f2

    def test_mixed_boards(self):
        resp = {'data': {'f58': 'X', 'f43': 100, 'f170': 0, 'f169': 0}}
        f = _CaptureFetcher(resp)
        f.get_index_realtime(['000001', '399001', '399006', '000300'])
        self.assertIn('secid=1.000001', f.urls[0])
        self.assertIn('secid=0.399001', f.urls[1])
        self.assertIn('secid=0.399006', f.urls[2])
        self.assertIn('secid=1.000300', f.urls[3])

    def test_null_data_skipped_silently(self):
        f = _CaptureFetcher({'data': None})
        df = f.get_index_realtime(['399001'])
        self.assertEqual(len(df), 0)


class TestStockRealtimeFields(unittest.TestCase):
    """同指数: stock/get 必须用 f43家族 + ÷100, 不能用 clist 的 f2/f3/f15家族。"""

    def test_stock_realtime_field_mapping(self):
        resp = {'data': {'f58': '贵州茅台', 'f43': 150000, 'f44': 151200,
                         'f45': 149000, 'f46': 149500, 'f47': 88888,
                         'f48': 1.3e10, 'f60': 148000,
                         'f169': 2000, 'f170': 135, 'f168': 45,
                         'f162': 2800, 'f167': 900, 'f116': 1.9e12, 'f117': 1.9e12}}
        f = _CaptureFetcher(resp)
        r = f.get_stock_realtime('600519')
        self.assertAlmostEqual(r['close'], 1500.00, places=2)
        self.assertAlmostEqual(r['high'], 1512.00, places=2)
        self.assertAlmostEqual(r['low'], 1490.00, places=2)
        self.assertAlmostEqual(r['open'], 1495.00, places=2)
        self.assertAlmostEqual(r['pre_close'], 1480.00, places=2)
        self.assertAlmostEqual(r['chg'], 20.00, places=2)
        self.assertAlmostEqual(r['chg_pct'], 1.35, places=2)
        self.assertAlmostEqual(r['turnover'], 0.45, places=2)
        self.assertAlmostEqual(r['pe'], 28.00, places=2)
        self.assertAlmostEqual(r['pb'], 9.00, places=2)
        self.assertIn('f43', f.urls[0])
        self.assertIn('secid=1.600519', f.urls[0])

    def test_stock_realtime_empty_on_null(self):
        f = _CaptureFetcher({'data': None})
        self.assertEqual(f.get_stock_realtime('600519'), {})


class TestLimitUpPool(unittest.TestCase):
    """修复回归: 涨停=东财涨停池口径, 不是涨幅前N名"""

    ZT_RESP = {'data': {'pool': [
        {'c': '301234', 'n': '创业板X', 'p': 12345, 'zdp': 19.98,
         'amount': 2.5e8, 'hs': 12.5, 'fbt': 93000, 'lbc': 2},
        {'c': '600519', 'n': '沪主板Y', 'p': 1500000, 'zdp': 10.0,
         'amount': 8e8, 'hs': 1.2, 'fbt': 92500, 'lbc': 1},
    ]}}

    def test_pool_parsing(self):
        f = _CaptureFetcher(self.ZT_RESP)
        df = f.get_limit_up(limit=100, date='20260930')
        self.assertEqual(len(df), 2)
        row = df[df['code'] == '301234'].iloc[0]
        self.assertEqual(row['lianban'], 2)
        self.assertAlmostEqual(row['close'], 12.345, places=2)
        self.assertAlmostEqual(row['chg_pct'], 19.98)
        self.assertIn('getTopicZTPool', f.urls[0])
        self.assertIn('date=20260930', f.urls[0])

    def test_limit_down_pool_endpoint(self):
        resp = {'data': {'pool': [
            {'c': '000004', 'n': '跌停Z', 'p': 5000, 'zdp': -10.0,
             'amount': 1e7, 'hs': 2.0, 'lbc': 1},
        ]}}
        f = _CaptureFetcher(resp)
        df = f.get_limit_down(limit=50)
        self.assertEqual(len(df), 1)
        self.assertIn('getTopicDTPool', f.urls[0])
        self.assertAlmostEqual(df.iloc[0]['chg_pct'], -10.0)

    def test_empty_pool(self):
        f = _CaptureFetcher({'data': {'pool': []}})
        df = f.get_limit_up()
        self.assertEqual(len(df), 0)

    def test_sector_overlap_removed(self):
        """gen_webdata_v2 板块跌幅榜必须排除涨幅榜前10(修复后逻辑)"""
        import src.sentiment.gen_webdata_v2 as gw
        sec = pd.DataFrame({
            '板块代码': [f'BK{i:04d}' for i in range(12)],
            '板块名称': [f'板块{i}' for i in range(12)],
            '涨跌幅': list(range(12, 0, -1)),
        })

        class _FakeFetcher:
            def get_index_realtime(self, codes=None):
                return pd.DataFrame()
            def get_limit_up(self, limit=200):
                return pd.DataFrame()
            def get_limit_down(self, limit=100):
                return pd.DataFrame()
            def get_sector_ranking(self, top_n=15):
                return sec
            def get_money_flow(self):
                return pd.DataFrame()

        import tempfile
        tmpdir = tempfile.mkdtemp()
        # gen_live_data 在函数内 from src.direct_data import get_fetcher → 需 patch 源模块
        with patch.object(gw, 'OUT', tmpdir), \
             patch('src.direct_data.get_fetcher', return_value=_FakeFetcher()):
            gw.gen_live_data()
        import json
        data = json.load(open(os.path.join(tmpdir, 'live.json'), encoding='utf-8'))
        top_codes = [s['板块代码'] for s in data['sectors_top']]
        bottom_codes = [s['板块代码'] for s in data['sectors_bottom']]
        self.assertEqual(len(top_codes), 10)
        self.assertFalse(set(top_codes) & set(bottom_codes), "涨跌幅榜重叠")


if __name__ == '__main__':
    unittest.main()
