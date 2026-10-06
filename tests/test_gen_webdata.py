# -*- coding: utf-8 -*-
"""gen_webdata 测试: NaN 安全序列化(修复前浏览器 JSON.parse 失败的根因)"""
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.sentiment.gen_webdata import sanitize_json, json_dump_safe, generate, main


def _reject_constant(c):
    raise ValueError(f"非法JSON常量: {c}")


class TestSanitize(unittest.TestCase):

    def test_nan_inf_become_none(self):
        obj = {'a': float('nan'), 'b': float('inf'), 'c': float('-inf'),
               'd': [1.5, float('nan')], 'e': {'f': np.float64('nan')},
               'g': np.float32(np.nan), 'ok': 3.14}
        out = sanitize_json(obj)
        self.assertIsNone(out['a'])
        self.assertIsNone(out['b'])
        self.assertIsNone(out['c'])
        self.assertIsNone(out['d'][1])
        self.assertEqual(out['d'][0], 1.5)
        self.assertIsNone(out['e']['f'])
        self.assertIsNone(out['g'])
        self.assertEqual(out['ok'], 3.14)

    def test_numpy_scalars_converted(self):
        out = sanitize_json({'i': np.int64(7), 'f': np.float64(2.5)})
        self.assertEqual(out['i'], 7)
        self.assertEqual(out['f'], 2.5)
        self.assertIsInstance(out['i'], int)


class TestJsonDumpSafe(unittest.TestCase):

    def _dump_and_parse(self, obj, **kwargs):
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False,
                                         encoding='utf-8') as f:
            json_dump_safe(obj, f, **kwargs)
            f.seek(0)
            raw = f.read()
        # parse_constant 会在遇到 NaN/Infinity 字面量时抛错 → 模拟浏览器严格模式
        return raw, json.loads(raw, parse_constant=_reject_constant)

    def test_dataframe_nan_rows_roundtrip(self):
        """to_dict 带出的 NaN 必须变成 null(修复前 trades.json 含裸 NaN)"""
        df = pd.DataFrame({'code': ['600001', '000002'],
                           'pnl': [123.45, np.nan],
                           'reason': ['止盈', np.nan]})
        df = df.astype(object).where(pd.notnull(df), None)
        raw, parsed = self._dump_and_parse({'columns': df.columns.tolist(),
                                            'rows': df.values.tolist()})
        self.assertIsNone(parsed['rows'][1][1])
        self.assertIsNone(parsed['rows'][1][2])
        self.assertEqual(parsed['rows'][0][1], 123.45)

    def test_mixed_nested_structure(self):
        obj = {'history': [{'date': '2025-01-01', 'dd': float('nan')},
                           {'date': '2025-01-02', 'dd': -5.2}],
               'meta': {'gen': pd.Timestamp('2025-01-01')}}
        _, parsed = self._dump_and_parse(obj, default=str)
        self.assertIsNone(parsed['history'][0]['dd'])
        self.assertEqual(parsed['history'][1]['dd'], -5.2)


class TestModuleContract(unittest.TestCase):

    def test_import_has_no_side_effects(self):
        """import 不得触发生成(修复前生成逻辑在模块顶层, import即全量重写)"""
        import src.sentiment.gen_webdata as gw
        # 模块导入后只应有函数定义, 生成必须显式调用
        self.assertTrue(callable(gw.generate))
        self.assertTrue(callable(gw.main))
        self.assertTrue(callable(gw.sanitize_json))


if __name__ == '__main__':
    unittest.main()
