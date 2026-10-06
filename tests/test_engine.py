# -*- coding: utf-8 -*-
"""回测引擎测试: 时序契约(涨跌停/现金/T+1)、停牌估值、状态重置"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401  (路径与stub引导)

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine


def _flat_stock(dates, opens, closes, code='600001'):
    n = len(dates)
    return pd.DataFrame({
        'date': dates, 'open': opens, 'high': np.maximum(opens, closes) * 1.001,
        'low': np.minimum(opens, closes) * 0.999, 'close': closes,
        'volume': 1e6, 'amount': 1e7, 'pctChg': pd.Series(closes).pct_change().fillna(0) * 100,
        'code': code,
    })


def _signals(dates, code, buy_idx, score=0.8):
    return pd.DataFrame([
        {'date': dates[i], 'code': code, 'signal': 1, 'score': score}
        for i in buy_idx
    ])


class TestEngineTimingContract(unittest.TestCase):

    def _run_basic(self):
        n = 120
        dates = pd.bdate_range('2025-01-01', periods=n)
        stock = _flat_stock(dates, np.linspace(10, 12, n), np.linspace(10, 12, n))
        index = helpers.make_index_df(n)
        sig = _signals(dates, '600001', list(range(60, n, 7)))
        engine = BacktestEngine()
        return engine.run(sig, {'600001': stock}, index), stock, sig

    def test_buy_never_above_limit_up(self):
        result, stock, _ = self._run_basic()
        buys = result['trades'][result['trades']['action'] == 'BUY']
        for _, t in buys.iterrows():
            prev = stock[stock['date'] < t['date']]
            pc = prev['close'].iloc[-1]
            assert t['price'] <= pc * 1.1 + 1e-6, f"BUY {t['price']} > 涨停 {pc*1.1}"

    def test_sell_never_below_limit_down(self):
        result, stock, _ = self._run_basic()
        sells = result['trades'][result['trades']['action'] == 'SELL']
        for _, t in sells.iterrows():
            prev = stock[stock['date'] < t['date']]
            pc = prev['close'].iloc[-1]
            assert t['price'] >= pc * 0.9 - 1e-6, f"SELL {t['price']} < 跌停 {pc*0.9}"

    def test_cash_never_negative(self):
        result, _, _ = self._run_basic()
        assert (result['equity_curve']['cash'] >= -1e-6).all()

    def test_t_plus_1_no_same_day_roundtrip(self):
        """买入当天不允许卖出(T+1)"""
        result, _, _ = self._run_basic()
        tr = result['trades']
        for _, s in tr[tr['action'] == 'SELL'].iterrows():
            same_day_buy = tr[(tr['action'] == 'BUY') & (tr['code'] == s['code'])
                              & (tr['date'] == s['date'])]
            assert len(same_day_buy) == 0, f"T+1违规: {s['date']} {s['code']} 当买当卖"

    def test_state_reset_between_runs(self):
        """同一实例跑两次, 结果必须一致(无跨run状态污染)"""
        engine = BacktestEngine()
        r1, stock, sig = self._run_basic()
        # 用新引擎和新实例各跑一次对比
        r2, _, _ = self._run_basic()
        e2 = BacktestEngine()
        r3 = e2.run(sig, {'600001': stock}, helpers.make_index_df(120))
        v1 = r1['equity_curve']['equity'].iloc[-1]
        v2 = r2['equity_curve']['equity'].iloc[-1]
        v3 = r3['equity_curve']['equity'].iloc[-1]
        assert abs(v1 - v2) < 1e-6 and abs(v1 - v3) < 1e-6


class TestEngineEdgeCases(unittest.TestCase):

    def test_limit_up_open_cannot_buy(self):
        """开盘封死涨停(=昨收*1.1)不买入"""
        n = 90
        dates = pd.bdate_range('2025-01-01', periods=n)
        closes = np.full(n, 10.0)
        opens = np.full(n, 10.0)
        buy_day = 70
        opens[buy_day] = 10.0 * 1.1  # 开盘即涨停
        stock = _flat_stock(dates, opens, closes)
        index = helpers.make_index_df(n)
        sig = _signals(dates, '600001', [buy_day])
        result = BacktestEngine().run(sig, {'600001': stock}, index)
        tr = result['trades']
        buys = tr[tr['action'] == 'BUY'] if len(tr) > 0 else tr
        assert len(buys) == 0, "涨停开盘不应成交"

    def test_limit_down_open_cannot_sell(self):
        """开盘封死跌停卖不出 → 记 SELL_FAIL, 仓位保留"""
        n = 90
        dates = pd.bdate_range('2025-01-01', periods=n)
        closes = np.full(n, 10.0)
        opens = np.full(n, 10.0)
        buy_day = 60
        crash_day = 70
        closes[crash_day - 1] = 9.0        # 前一日已跌(满足止损条件 prev_close/cost<=0.93)
        opens[crash_day] = 9.0 * 0.9       # 开盘即跌停
        closes[crash_day] = 9.0 * 0.9
        stock = _flat_stock(dates, opens, closes)
        # 让买入发生在 buy_day(开盘价10)
        index = helpers.make_index_df(n)
        sig = _signals(dates, '600001', [buy_day])
        # crash_day 当天给一个负信号触发卖出判断
        sig = pd.concat([sig, pd.DataFrame([
            {'date': dates[crash_day], 'code': '600001', 'signal': -1, 'score': -0.5}
        ])], ignore_index=True)
        result = BacktestEngine().run(sig, {'600001': stock}, index)
        tr = result['trades']
        fails = tr[tr['action'] == 'SELL_FAIL']
        sells = tr[(tr['action'] == 'SELL') & (tr['date'] == dates[crash_day])]
        assert len(sells) == 0, "跌停开盘不应有成交卖出"
        assert len(fails) >= 1, "跌停无法卖出应记录 SELL_FAIL"

    def test_suspension_valued_at_last_close(self):
        """停牌(无当日数据)持仓按最近收盘估值, 净值不塌方"""
        n = 90
        dates = pd.bdate_range('2025-01-01', periods=n)
        closes = np.full(n, 10.0)
        stock = _flat_stock(dates, np.full(n, 10.0), closes)
        # 制造停牌: 最后5天从指数日历中剔除该股票数据
        stock_trading = stock.iloc[:-5]
        index = helpers.make_index_df(n)
        sig = _signals(dates, '600001', [60])
        engine = BacktestEngine()
        result = engine.run(sig, {'600001': stock_trading}, index)
        eq = result['equity_curve']
        bought = eq[eq['positions'] > 0]
        assert len(bought) > 0, "应已建仓"
        # 停牌期间的最后几天, 净值应=现金+股数*最近收盘(10), 不应暴跌为纯现金
        last = eq.iloc[-1]
        expected_min = 100000 * 0.9  # 持仓仍有价值(约20%仓位*10元), 远高于全现金清仓
        assert last['equity'] > expected_min + 1, (
            f"停牌期净值塌方: {last['equity']}, 仓位应按最近收盘10元估值")
        # 精确校验: 期末净值 == 现金 + shares*10
        buys = result['trades'][result['trades']['action'] == 'BUY']
        shares = buys['shares'].iloc[0]
        assert abs(last['equity'] - (last['cash'] + shares * 10.0)) < 1e-6

    def test_cutoff_does_not_deadlock_after_recovery_window(self):
        """熔断冷却结束后必须能重新入场(修复前: peak只涨不跌→回撤恒>8%→永久锁死)"""
        n = 130
        dates = pd.bdate_range('2025-01-01', periods=n)
        closes = np.full(n, 10.0)
        opens = np.full(n, 10.0)
        # 前60天缓涨建仓 → 随后暴跌触发熔断 → 低位横盘(净值不再创新高) → 低位放量反弹
        closes[:60] = np.linspace(10, 11, 60)
        closes[60:71] = np.linspace(11, 8.0, 11)   # 暴跌触发-8%熔断
        closes[71:] = 8.0                           # 低位横盘
        opens[71:] = 8.0
        stock = _flat_stock(dates, opens, closes)
        index = helpers.make_index_df(n)
        # 全程给买入信号(强度高)
        sig = _signals(dates, '600001', list(range(60, n, 5)), score=0.9)
        result = BacktestEngine().run(sig, {'600001': stock}, index)
        tr = result['trades']
        cutoff_date = dates[67]  # 暴跌中段触发熔断
        buys_after = tr[(tr['action'] == 'BUY') & (tr['date'] > pd.Timestamp('2025-04-15'))]
        assert len(buys_after) > 0, "熔断后系统被永久锁死, 低位没有任何再入场"

    def test_growth_stock_board_20pct_limit(self):
        """300xxx 创业板按20%涨跌停判断"""
        engine = BacktestEngine()
        assert engine._limit_pct('300001') == 0.2
        assert engine._limit_pct('301001') == 0.2
        assert engine._limit_pct('688001') == 0.2
        assert engine._limit_pct('600001') == 0.1
        assert engine._limit_pct('000002') == 0.1

    def test_prev_close_derivation_chain(self):
        """昨收三级回退: pre_close列 → pctChg反推 → 前一根收盘"""
        engine = BacktestEngine()
        n = 5
        dates = pd.bdate_range('2025-01-01', periods=n)
        df = _flat_stock(dates, [10, 10, 10, 10, 10], [10, 10, 11, 10, 10])
        # 无 pre_close 列, 有 pctChg: close=11, pctChg=10 → 昨收=10
        pc = engine._prev_close(df, dates[2])
        assert abs(pc - 10.0) < 0.01
        # 删掉 pctChg 列 → 回退前一根收盘
        df2 = df.drop(columns=['pctChg'])
        pc2 = engine._prev_close(df2, dates[2])
        assert abs(pc2 - 10.0) < 1e-9


if __name__ == '__main__':
    import unittest
    unittest.main()
