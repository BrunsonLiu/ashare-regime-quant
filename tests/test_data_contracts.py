# -*- coding: utf-8 -*-
"""数据契约冒烟测试: 对仓库内的真实数据文件断言 schema(见 ARCHITECTURE.md 契约表)

daily/index 缓存不入库(CI 无此文件)时自动跳过。
"""
import json
import os
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
WEB = os.path.join(ROOT, 'web', 'data')


def _skip_unless(path):
    return unittest.skipUnless(os.path.exists(path), f'{path} 不存在(CI 环境正常)')


class TestTrackedContracts(unittest.TestCase):
    """随仓库走的数据文件, CI 必须存在"""

    def test_sentiment_3y_schema(self):
        df = pd.read_csv(os.path.join(DATA, 'sentiment_3y.csv'))
        for col in ['date', 'zt_count', 'zhaban_count', 'zhaban_rate',
                    'lianban_height', 'lianban2', 'lianban3', 'lianban4p', 'shouban']:
            self.assertIn(col, df.columns)

    def test_event_files_headerless(self):
        for name, names in [('zt_events.csv', ['date', 'code', 'lianban']),
                            ('zhaban_events.csv', ['date', 'code'])]:
            path = os.path.join(DATA, name)
            if not os.path.exists(path):
                self.skipTest(f'{name} 不存在')
            # code 是带前导零的6位文本, 必须显式str读取(否则000001被推断成1)
            df = pd.read_csv(path, header=None, names=names, dtype={'code': str})
            self.assertGreater(len(df), 0)
            dates = pd.to_datetime(df['date'], errors='coerce')
            self.assertEqual(dates.isna().sum(), 0, f'{name} 存在非法日期')
            self.assertTrue((df['code'].str.len() == 6).all(),
                            f'{name} 存在非6位代码')

    def test_web_json_strict(self):
        """所有 web JSON 必须浏览器严格合法(无 NaN/Infinity 字面量)"""
        def reject(c):
            raise ValueError(f'非法JSON常量: {c}')
        files = [f for f in os.listdir(WEB) if f.endswith('.json')]
        self.assertTrue(files)
        for f in files:
            with open(os.path.join(WEB, f), encoding='utf-8') as fh:
                json.loads(fh.read(), parse_constant=reject)


class TestLocalCacheContracts(unittest.TestCase):
    """本地缓存(不入库), 存在时校验"""

    @_skip_unless(os.path.join(DATA, 'daily'))
    def test_daily_cache_schema(self):
        daily = os.path.join(DATA, 'daily')
        sample = sorted(f for f in os.listdir(daily) if f.endswith('.csv'))[0]
        df = pd.read_csv(os.path.join(daily, sample))
        for col in ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']:
            self.assertIn(col, df.columns, f'daily 缓存 schema 漂移: 缺 {col}')

    @_skip_unless(os.path.join(DATA, 'index_000001.csv'))
    def test_index_cache_schema(self):
        df = pd.read_csv(os.path.join(DATA, 'index_000001.csv'))
        for col in ['date', 'open', 'high', 'low', 'close', 'volume']:
            self.assertIn(col, df.columns, f'指数缓存 schema 漂移: 缺 {col}')

    @_skip_unless(os.path.join(DATA, 'backtest_equity.csv'))
    def test_backtest_output_schema(self):
        df = pd.read_csv(os.path.join(DATA, 'backtest_equity.csv'))
        for col in ['date', 'equity', 'cash', 'positions', 'regime', 'position_pct']:
            self.assertIn(col, df.columns)


if __name__ == '__main__':
    unittest.main()
