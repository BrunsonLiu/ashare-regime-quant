# -*- coding: utf-8 -*-
"""四环境分类测试: 判定优先级、无前视、分布合理性"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.utils.market_env import MarketEnvironment, ENV_A, ENV_B, ENV_C, ENV_D, ENV_EXPOSURE


def _index(closes):
    n = len(closes)
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({'date': pd.bdate_range('2024-01-01', periods=n),
                         'open': c, 'high': c * 1.01, 'low': c * 0.99,
                         'close': c, 'volume': 1e8, 'amount': 1e10})


def _sentiment(dates, zt, lb, zr):
    return pd.DataFrame({'date': dates, 'zt_count': zt, 'lianban_height': lb,
                         'zhaban_rate': zr})


class TestClassification(unittest.TestCase):

    def test_bear_has_top_priority(self):
        """均线空头+深跌 → D(最高优先级, 即使情绪数据很好看)"""
        n = 120
        closes = np.concatenate([np.full(70, 3200.0), np.linspace(3200, 2900, 50)])
        idx = _index(closes)
        s = _sentiment(idx['date'], zt=80, lb=5, zr=0.15)  # 情绪"很好"
        env = MarketEnvironment()
        envs, df = env.classify_series(idx, s)
        # 末段是深跌 → 应为 D, 不该被情绪带成 A
        self.assertEqual(envs[idx['date'].iloc[-1]], ENV_D)

    def test_main_line_needs_zt_and_height(self):
        """涨停多但连板高度不足 → 不算A(主线需连板高度)"""
        n = 120
        idx = _index(np.linspace(3000, 3100, n))  # 温和上涨(非熊非急跌)
        s = _sentiment(idx['date'], zt=80, lb=1, zr=0.15)  # 涨停多但高度=1
        env = MarketEnvironment()
        envs, _ = env.classify_series(idx, s)
        self.assertNotEqual(envs[idx['date'].iloc[-1]], ENV_A)
        # 高度≥3 才是 A
        s2 = _sentiment(idx['date'], zt=80, lb=4, zr=0.15)
        envs2, _ = MarketEnvironment().classify_series(idx, s2)
        self.assertEqual(envs2[idx['date'].iloc[-1]], ENV_A)

    def test_crash_is_env_c(self):
        """5日急跌但未到熊市深度(均线未死叉) → C 超跌"""
        n = 120
        # 长期温和上行, 末端急跌约7%(超5日阈值), 但MA20仍高于MA60*0.98 → 不触发D
        closes = np.concatenate([np.linspace(3000, 3400, 114), np.linspace(3400, 3150, 6)])
        idx = _index(closes)
        s = _sentiment(idx['date'], zt=45, lb=2, zr=0.30)
        envs, df = MarketEnvironment().classify_series(idx, s)
        last = idx['date'].iloc[-1]
        # 确认没被D抢走(MA20未死叉)
        self.assertNotEqual(envs[last], ENV_D, "该用例不应触发熊市判定")
        self.assertEqual(envs[last], ENV_C)

    def test_no_lookahead(self):
        """T日环境判定必须只用 T-1 及之前数据: 变更末日数据不应改变前一日判定"""
        n = 120
        idx = _index(np.linspace(3000, 3200, n))
        s = _sentiment(idx['date'], zt=80, lb=4, zr=0.15)
        env = MarketEnvironment()
        envs_a, _ = env.classify_series(idx, s)
        # 篡改末日情绪(极端值), 前一日判定不应变
        s_b = s.copy()
        s_b.loc[s_b.index[-1], 'zt_count'] = 9999
        envs_b, _ = env.classify_series(idx, s_b)
        d_prev = idx['date'].iloc[-2]
        self.assertEqual(envs_a[d_prev], envs_b[d_prev],
                         "T-1日判定被T日数据影响 → 前视")

    def test_warmup_before_ma_long(self):
        n = 120
        idx = _index(np.linspace(3000, 3100, n))
        s = _sentiment(idx['date'], zt=80, lb=4, zr=0.15)
        envs, _ = MarketEnvironment().classify_series(idx, s)
        self.assertEqual(envs[idx['date'].iloc[0]], 'WARMUP')

    def test_exposure_mapping(self):
        self.assertEqual(ENV_EXPOSURE[ENV_D], 0.00)   # 熊市空仓
        self.assertEqual(ENV_EXPOSURE[ENV_A], 0.80)   # 主线重仓
        self.assertGreater(ENV_EXPOSURE[ENV_A], ENV_EXPOSURE[ENV_B])  # A>B


if __name__ == '__main__':
    unittest.main()
