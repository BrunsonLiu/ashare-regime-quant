"""
仓位管理器 - 敌进我退，保存实力

核心原则：
1. 市场状态决定仓位上限（战略层面）
2. 单只股票仓位由信号强度决定（战术层面）
3. 连续亏损自动降仓（持久战，保存实力）
4. 止损纪律无条件执行
"""
import pandas as pd
import numpy as np
from config import TRADE_CONFIG


class PositionManager:
    """仓位管理器"""

    def __init__(self):
        self.cfg = TRADE_CONFIG
        self.initial_capital = self.cfg['initial_capital']
        self.max_positions = self.cfg['max_positions']
        self.position_pct = self.cfg['position_pct']
        self.commission = self.cfg['commission_rate']
        self.stamp_tax = self.cfg['stamp_tax']
        self.slippage = self.cfg['slippage']

        # 连续亏损追踪
        self.consecutive_losses = 0
        self.loss_cooldown = 0  # 冷却期（天数）

        # 止损止盈
        self.stop_loss = -0.07      # 单只止损7%
        self.take_profit = 0.15     # 单只止盈15%
        self.trailing_stop = 0.05   # 移动止盈5%（盈利超过10%后启动）

    def get_target_positions(self, regime_advice):
        """根据市场状态获取仓位配置"""
        max_holdings = regime_advice['max_holdings']
        max_pos_pct = regime_advice['max_position_pct']
        single_pct = regime_advice['single_position_pct']

        # 连续亏损冷却期：强制降仓（保存实力）
        if self.consecutive_losses >= 3:
            max_holdings = 1
            max_pos_pct = 0.15
            single_pct = 0.15
            print(f"  [!] 连续亏损{self.consecutive_losses}次，进入冷却期，仓位降至15%")

        return {
            'max_holdings': max_holdings,
            'max_position_pct': max_pos_pct,
            'single_position_pct': single_pct,
            'in_cooldown': self.consecutive_losses >= 3,
        }

    def calc_position_size(self, capital, price, signal_strength, pos_config):
        """
        计算单只股票的买入数量
        信号越强，仓位越大（集中优势兵力）
        """
        # 基础仓位
        base_value = capital * pos_config['single_position_pct']

        # 信号强度调整：0.5~1.0的信号，仓位50%~100%
        strength_multiplier = max(0.5, min(1.0, signal_strength))
        target_value = base_value * strength_multiplier

        # 不超过总资金的max_position_pct
        max_value = capital * pos_config['max_position_pct']
        target_value = min(target_value, max_value)

        # 整手计算
        shares = int(target_value / price / 100) * 100
        return max(shares, 0)

    def check_stop_loss(self, position, current_price):
        """
        止损检查（纪律无条件执行）
        返回: (should_sell, reason)
        """
        cost = position['cost']
        pnl_pct = (current_price - cost) / cost

        # 硬止损
        if pnl_pct <= self.stop_loss:
            return True, f"止损: {pnl_pct*100:.1f}%"

        # 止盈
        if pnl_pct >= self.take_profit:
            return True, f"止盈: {pnl_pct*100:.1f}%"

        # 移动止盈：盈利超过10%后，回撤5%就卖
        if pnl_pct >= 0.10:
            if 'peak' not in position:
                position['peak'] = current_price
            else:
                position['peak'] = max(position['peak'], current_price)
                drawdown = (current_price - position['peak']) / position['peak']
                if drawdown <= -self.trailing_stop:
                    return True, f"移动止盈: 回撤{drawdown*100:.1f}%"

        return False, ""

    def update_loss_tracking(self, trade_result):
        """更新连续亏损计数"""
        if trade_result < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # 冷却期递减
        if self.loss_cooldown > 0:
            self.loss_cooldown -= 1

    def can_trade(self):
        """是否可以交易（冷却期检查）"""
        if self.consecutive_losses >= 5:
            print("  [!] 连续亏损5次，建议暂停交易，重新审视策略")
            return False
        return True
