# -*- coding: utf-8 -*-
"""仓位管理测试: 连亏冷却不死锁、组合资产基准sizing、止损止盈"""
import os
import sys
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

from src.utils.position_manager import PositionManager


class TestLossCooldown(unittest.TestCase):

    def test_five_losses_trigger_cooldown_then_recover(self):
        """连亏5次 → 暂停10个交易日后自动恢复(修复前: 无持仓时永久死锁)"""
        pm = PositionManager()
        with redirect_stdout(io.StringIO()):
            for _ in range(5):
                pm.update_loss_tracking(-100)
        self.assertFalse(pm.can_trade())
        self.assertEqual(pm.loss_cooldown, 10)
        # 每交易日 tick 一次
        for _ in range(10):
            pm.tick_cooldown()
        self.assertTrue(pm.can_trade())
        # 冷却结束后仍保持降仓状态(连亏计数=3)
        self.assertEqual(pm.consecutive_losses, 3)
        cfg = pm.get_target_positions(
            {'max_holdings': 5, 'max_position_pct': 1.0, 'single_position_pct': 0.25})
        self.assertEqual(cfg['max_holdings'], 1)

    def test_win_resets_counter(self):
        pm = PositionManager()
        pm.update_loss_tracking(-100)
        pm.update_loss_tracking(-100)
        pm.update_loss_tracking(50)
        self.assertEqual(pm.consecutive_losses, 0)
        self.assertTrue(pm.can_trade())


class TestSizing(unittest.TestCase):

    def test_sizing_on_portfolio_base(self):
        """sizing 基准=组合总资产: 10万×20%×强度1.0 @10元 → 2000股"""
        pm = PositionManager()
        cfg = {'single_position_pct': 0.2, 'max_position_pct': 0.6}
        shares = pm.calc_position_size(100000, 10.0, 1.0, cfg)
        self.assertEqual(shares, 2000)

    def test_strength_multiplier_floor(self):
        """弱信号强度下限0.5: 10万×20%×0.5 @10元 → 1000股"""
        pm = PositionManager()
        cfg = {'single_position_pct': 0.2, 'max_position_pct': 0.6}
        shares = pm.calc_position_size(100000, 10.0, 0.1, cfg)
        self.assertEqual(shares, 1000)

    def test_zero_when_price_too_high(self):
        pm = PositionManager()
        cfg = {'single_position_pct': 0.2, 'max_position_pct': 0.6}
        shares = pm.calc_position_size(10000, 500.0, 1.0, cfg)  # 2000元买不了一手
        self.assertEqual(shares, 0)


class TestStops(unittest.TestCase):

    def test_hard_stop_loss(self):
        """中长线止损-15%(原-7%为短线口径, 会砍掉正常波动)"""
        pm = PositionManager()
        should, reason = pm.check_stop_loss({'cost': 10.0}, 8.4)   # -16%
        self.assertTrue(should)
        self.assertIn('止损', reason)
        # -8% 不应触发中长线止损(短线才触发)
        should2, _ = pm.check_stop_loss({'cost': 10.0}, 9.2)
        self.assertFalse(should2, '中长线-15%止损不应被-8%波动打穿')

    def test_take_profit_disabled(self):
        """中长线不止盈(take_profit=0, 让利润奔跑)"""
        pm = PositionManager()
        should, _ = pm.check_stop_loss({'cost': 10.0}, 15.0)   # +50%
        self.assertFalse(should, '中长线不应有固定止盈')

    def test_no_stop_in_range(self):
        pm = PositionManager()
        should, _ = pm.check_stop_loss({'cost': 10.0}, 10.3)
        self.assertFalse(should)


if __name__ == '__main__':
    unittest.main()
