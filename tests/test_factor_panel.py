# -*- coding: utf-8 -*-
"""因子面板等价性测试: 向量化路径必须与旧的逐日切片路径严格一致

这是"后视纯"契约的执行者: 任何未来写出的因子若使用全样本统计/未来数据,
此测试会当场失败(见 ARCHITECTURE.md 回测时序契约)。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

import numpy as np
import pandas as pd

from src.strategy.multi_factor import MultiFactorStrategy


def _make_data(n_stocks=6, n_days=150, seed=3):
    rng = np.random.default_rng(seed)
    data = {}
    for k in range(n_stocks):
        code = f'60000{k}'
        ret = rng.normal(0.0004, 0.018, n_days)
        close = 10 * (1 + k * 0.5) * np.cumprod(1 + ret)
        openc = close * (1 + rng.normal(0, 0.004, n_days))
        vol = rng.uniform(1e6, 5e6, n_days)
        df = pd.DataFrame({
            'date': pd.bdate_range('2024-01-01', periods=n_days),
            'open': openc,
            'high': np.maximum(openc, close) * 1.005,
            'low': np.minimum(openc, close) * 0.995,
            'close': close,
            'volume': vol,
            'amount': vol * close,
            'turnover': rng.uniform(0.5, 8, n_days),
            'pe': rng.uniform(10, 60, n_days),
            'pb': rng.uniform(0.8, 6, n_days),
            'roe': rng.normal(10, 2, n_days).cumsum() / n_days * 10 + 10,
            'revenue': np.abs(rng.normal(100, 5, n_days).cumsum()),
            'total_mv': rng.uniform(5e9, 5e10, n_days),
            'code': code,
        })
        data[code] = df
    return data


class TestPanelEquivalence(unittest.TestCase):
    """新面板路径 ≡ 旧切片路径(全部注册因子 × 多个日期)"""

    def test_panel_equals_per_slice(self):
        strategy = MultiFactorStrategy()
        data = _make_data()
        panels = strategy.precompute_factor_panels(data)

        factor_names = sorted(set().union(
            *[set(strategy.regime.get_factor_weights(r).keys())
              for r in ('BULL', 'BEAR', 'SHOCK')]))
        factor_names = [f for f in factor_names if f in strategy.engine.factors]
        self.assertTrue(factor_names)

        index_df = helpers.make_index_df(150)
        all_dates = sorted(pd.to_datetime(index_df['date'].unique()))

        # 抽查多个日期(覆盖前中后段)
        for T in [all_dates[80], all_dates[100], all_dates[120], all_dates[149]]:
            records = strategy.cross_section_records(panels, all_dates)[T]
            self.assertTrue(records, f"{T} 无记录")
            by_code = {r['code']: r for r in records}
            for code, df in data.items():
                if code not in by_code:
                    continue
                df_u = df[df['date'] < T]  # 旧路径: T-1收盘切片
                self.assertGreaterEqual(len(df_u), 60)
                for fname in factor_names:
                    f = strategy.engine.factors[fname]
                    old_v = f.get_latest(df_u)
                    new_v = by_code[code][fname]
                    if pd.isna(old_v) and (new_v is None or np.isnan(new_v)):
                        continue
                    self.assertAlmostEqual(
                        float(old_v), float(new_v), places=8,
                        msg=f"因子 {fname} 在 {T.date()} {code} 面板值与切片值不等: "
                            f"{old_v} vs {new_v} —— 因子不再是后视纯!")

    def test_60_row_history_rule(self):
        """不足60行历史的股票不进横截面(与旧路径 mask.sum()>=60 一致)"""
        strategy = MultiFactorStrategy()
        data = _make_data()
        # 把一只股票砍短
        short_code = '600000'
        data[short_code] = data[short_code].iloc[:50].copy()
        panels = strategy.precompute_factor_panels(data)
        index_df = helpers.make_index_df(150)
        all_dates = sorted(pd.to_datetime(index_df['date'].unique()))
        records = strategy.cross_section_records(panels, all_dates)[all_dates[100]]
        codes = {r['code'] for r in records}
        self.assertNotIn(short_code, codes, "不足60行历史的股票不应出现在横截面中")

    def test_prosperity_is_backward_pure(self):
        """ProsperityFactor 专项: 扩展窗口标准化后必须后视纯"""
        strategy = MultiFactorStrategy()
        data = _make_data(n_stocks=2)
        f = strategy.engine.factors['prosperity']
        df = data['600001']
        full = f.calculate(df)
        for t in [100, 120, 149]:
            sliced = f.calculate(df.iloc[:t + 1])
            self.assertAlmostEqual(
                float(full.iloc[t]), float(sliced.iloc[-1]), places=8,
                msg="ProsperityFactor 第t行值依赖了>t的数据(未来函数)")


if __name__ == '__main__':
    unittest.main()
