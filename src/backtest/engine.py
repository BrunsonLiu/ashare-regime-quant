"""
回测引擎 - 模拟T+1交易，融入毛选思想

特性：
1. 市场状态自适应仓位（敌进我退）
2. 止损止盈纪律（保存实力）
3. 连续亏损冷却期（持久战）
4. 涨跌停限制（A股特殊规则）
5. 手续费、印花税、滑点
"""
import pandas as pd
import numpy as np
from config import TRADE_CONFIG, PORTFOLIO_RISK_CONFIG
from src.utils.position_manager import PositionManager
from src.utils.market_regime import MarketRegime


class BacktestEngine:
    """T+1回测引擎"""

    def __init__(self):
        self.cfg = TRADE_CONFIG
        self.initial_capital = self.cfg['initial_capital']
        self.commission = self.cfg['commission_rate']
        self.stamp_tax = self.cfg['stamp_tax']
        self.slippage = self.cfg['slippage']

        self.pos_manager = PositionManager()
        self.regime = MarketRegime()
        self.risk_cfg = PORTFOLIO_RISK_CONFIG
        self.cutoff_cooldown = 0  # 熔断冷却剩余天数
        self.peak_equity = self.initial_capital  # 组合净值高点

    def run(self, signals, daily_data, index_df=None):
        """
        运行回测

        决策/成交时序（消除前视偏差）:
        - 信号与决策基于 T-1 收盘数据
        - 成交按 T 日开盘价 ± 滑点
        - T 日收盘价仅用于当日净值盯市

        参数:
            signals: DataFrame[date, code, signal(-1~1), score]
                     date=T 的信号必须由 < T 的数据算出（T-1收盘决策）
            daily_data: dict {code: DataFrame[date, open, high, low, close, volume, amount]}
            index_df: 指数日线数据（用于市场状态判断）

        返回: dict {equity_curve, trades, stats, regime_history}
        """
        # 重置实例状态，避免同一实例多次 run() 继承上次的高点/冷却/连亏
        capital = self.initial_capital
        self.cutoff_cooldown = 0
        self.peak_equity = self.initial_capital
        self.pos_manager.consecutive_losses = 0
        self.pos_manager.loss_cooldown = 0
        positions = {}  # {code: {'shares': n, 'cost': price, 'buy_date': date}}
        trades = []
        equity_records = []
        regime_history = []

        # 遍历完整交易日（含前期无信号空仓段），保证净值曲线从初始资金起、不丢段
        if index_df is not None and 'date' in index_df.columns and len(index_df) > 0:
            all_dates = sorted(index_df['date'].unique())
        elif 'date' in signals.columns:
            all_dates = sorted(signals['date'].unique())
        else:
            all_dates = []

        for date in all_dates:
            day_signals = signals[signals['date'] == date]

            # 冷却期倒计时（每个交易日一次）
            self.pos_manager.tick_cooldown()

            # === 1. 市场状态判断（调查研究）===
            market_state = None
            if index_df is not None:
                # 决策只用 T-1 及之前的数据（T 日收盘尚未发生）
                index_up_to = index_df[index_df['date'] < date]
                if len(index_up_to) >= 60:
                    market_state = self.regime.detect(index_up_to)
                    regime_name = market_state['regime']
                    pos_advice = market_state['position_advice']
                    pos_config = self.pos_manager.get_target_positions(pos_advice)

                    regime_history.append({
                        'date': date,
                        'regime': regime_name,
                        'max_holdings': pos_config['max_holdings'],
                        'max_pos_pct': pos_config['max_position_pct'],
                    })
                else:
                    pos_config = {
                        'max_holdings': 3,
                        'max_position_pct': 0.6,
                        'single_position_pct': 0.2,
                        'in_cooldown': False,
                    }
                    regime_name = "UNKNOWN"
            else:
                pos_config = {
                    'max_holdings': self.cfg['max_positions'],
                    'max_position_pct': 1.0,
                    'single_position_pct': self.cfg['position_pct'],
                    'in_cooldown': False,
                }
                regime_name = "UNKNOWN"

            # === 组合级熔断：净值回撤超过阈值 → 强制清仓 + 冷却 ===
            # 用 T-1 收盘估值做决策（T 开盘成交），停牌持仓沿用最近收盘
            current_total_value = capital
            for code, pos in positions.items():
                stock_df = daily_data.get(code)
                if stock_df is not None:
                    pc = self._prev_close(stock_df, date)
                    if pc is not None:
                        current_total_value += pos['shares'] * pc

            self.peak_equity = max(self.peak_equity, current_total_value)
            current_drawdown = (current_total_value - self.peak_equity) / self.peak_equity

            if current_drawdown <= self.risk_cfg['max_drawdown_cutoff'] and self.cutoff_cooldown <= 0:
                # 触发熔断：全部卖出 + 进入冷却
                print(f"  [CUTOFF] {date} 回撤{current_drawdown*100:.1f}% 触发组合熔断，强制清仓")
                self.cutoff_cooldown = self.risk_cfg['cutoff_cooldown']
                # 强制卖出所有持仓
                for code in list(positions.keys()):
                    if code not in daily_data:
                        continue
                    stock_df = daily_data[code]
                    day_data = stock_df[stock_df['date'] == date]
                    if len(day_data) == 0:
                        continue
                    open_price = day_data['open'].iloc[0]
                    sell_price, can_sell = self._executable_sell_price(code, open_price, stock_df, date)
                    if not can_sell:
                        trades.append({
                            'date': date, 'code': code, 'action': 'SELL_FAIL',
                            'price': open_price, 'shares': positions[code]['shares'],
                            'reason': '熔断清仓跌停无法卖出', 'pnl': 0
                        })
                        continue
                    shares = positions[code]['shares']
                    cost = positions[code]['cost']
                    proceeds = shares * sell_price
                    trade_cost = proceeds * (self.commission + self.stamp_tax)
                    pnl = shares * (sell_price - cost) - trade_cost
                    capital += proceeds - trade_cost
                    self.pos_manager.update_loss_tracking(pnl)
                    trades.append({
                        'date': date, 'code': code, 'action': 'SELL',
                        'price': round(sell_price, 2), 'shares': shares,
                        'cost_basis': round(cost, 2), 'pnl': round(pnl, 2),
                        'pnl_pct': round((sell_price / cost - 1) * 100, 2),
                        'reason': '组合熔断清仓',
                        'commission': round(trade_cost, 2)
                    })
                    del positions[code]

            if self.cutoff_cooldown > 0:
                self.cutoff_cooldown -= 1
                # 熔断冷却期内：空仓观望，不买入
                skip_buy = True
            else:
                skip_buy = False

            # === 指数破位：停止开仓 ===
            index_break = False
            if index_df is not None and len(index_up_to) >= 60:
                idx_close = index_up_to['close']
                ma20 = idx_close.rolling(20).mean().iloc[-1]
                ma60 = idx_close.rolling(60).mean().iloc[-1]
                recent20_ret = (idx_close.iloc[-1] / idx_close.iloc[-20] - 1) if len(idx_close) >= 20 else 0
                if ma20 < ma60 * 0.99 and recent20_ret < self.risk_cfg['index_break_threshold']:
                    index_break = True
                    print(f"  [INDEX_BREAK] {date} 指数破位 (MA20<{ma60*0.99:.0f}, 20日{recent20_ret*100:.1f}%) 停止开仓")

            # BEAR 状态或指数破位 → 空仓/停止买入（保存实力）
            if regime_name == "BEAR" or index_break:
                skip_buy = True

                # 若配置启用，清仓观望（熊市不持股，保存实力）
                if self.risk_cfg.get('bear_clear_positions', False) and len(positions) > 0:
                    print(f"  [BEAR_CLEAR] {date} 市场进入{regime_name}，清仓观望")
                    for code in list(positions.keys()):
                        if code not in daily_data:
                            continue
                        stock_df = daily_data[code]
                        day_data = stock_df[stock_df['date'] == date]
                        if len(day_data) == 0:
                            continue
                        open_price = day_data['open'].iloc[0]
                        sell_price, can_sell = self._executable_sell_price(code, open_price, stock_df, date)
                        if not can_sell:
                            trades.append({
                                'date': date, 'code': code, 'action': 'SELL_FAIL',
                                'price': open_price, 'shares': positions[code]['shares'],
                                'reason': 'BEAR清仓跌停无法卖出', 'pnl': 0
                            })
                            continue
                        shares = positions[code]['shares']
                        cost = positions[code]['cost']
                        proceeds = shares * sell_price
                        trade_cost = proceeds * (self.commission + self.stamp_tax)
                        pnl = shares * (sell_price - cost) - trade_cost
                        capital += proceeds - trade_cost
                        self.pos_manager.update_loss_tracking(pnl)
                        trades.append({
                            'date': date, 'code': code, 'action': 'SELL',
                            'price': round(sell_price, 2), 'shares': shares,
                            'cost_basis': round(cost, 2),
                            'pnl': round(pnl, 2),
                            'pnl_pct': round((sell_price / cost - 1) * 100, 2),
                            'reason': f'{regime_name}状态清仓观望',
                            'commission': round(trade_cost, 2)
                        })
                        del positions[code]

            # === 2. 卖出（T+1 + 止损止盈）===
            for code in list(positions.keys()):
                if code not in daily_data:
                    continue

                stock_df = daily_data[code]
                day_data = stock_df[stock_df['date'] == date]

                if len(day_data) == 0:
                    continue

                # 止损止盈用 T-1 收盘判断（决策先于 T 开盘成交）
                prev_close = self._prev_close(stock_df, date)
                if prev_close is None:
                    continue

                # 检查止损止盈
                should_sell, reason = self.pos_manager.check_stop_loss(
                    positions[code], prev_close
                )

                # 信号转负也卖（signals 的 date=T 信号由 <T 数据算出，无前视）
                if not should_sell:
                    sig = day_signals[day_signals['code'] == code]
                    if len(sig) > 0 and sig['signal'].iloc[0] < 0:
                        should_sell = True
                        reason = "信号转负"

                # T+1检查：买入当天不能卖
                if should_sell and positions[code].get('buy_date') == date:
                    should_sell = False  # T+1限制

                if should_sell:
                    open_price = day_data['open'].iloc[0]
                    sell_price, can_sell = self._executable_sell_price(code, open_price, stock_df, date)
                    if not can_sell:
                        trades.append({
                            'date': date, 'code': code, 'action': 'SELL_FAIL',
                            'price': open_price, 'shares': positions[code]['shares'],
                            'reason': '跌停无法卖出', 'pnl': 0
                        })
                        continue

                    shares = positions[code]['shares']
                    cost = positions[code]['cost']
                    proceeds = shares * sell_price
                    trade_cost = proceeds * (self.commission + self.stamp_tax)
                    pnl = shares * (sell_price - cost) - trade_cost
                    capital += proceeds - trade_cost

                    # 更新连续亏损
                    self.pos_manager.update_loss_tracking(pnl)

                    trades.append({
                        'date': date, 'code': code, 'action': 'SELL',
                        'price': round(sell_price, 2), 'shares': shares,
                        'cost_basis': round(cost, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round((sell_price / cost - 1) * 100, 2),
                        'reason': reason,
                        'commission': round(trade_cost, 2)
                    })
                    del positions[code]

            # === 3. 买入（集中优势兵力）===
            # 只有在未触发风控、未熔断、非熊市破位、且允许交易时才买入
            if not skip_buy and self.pos_manager.can_trade():
                buy_signals = day_signals[
                    day_signals['signal'] > 0
                ].sort_values('score', ascending=False)

                max_new = pos_config['max_holdings'] - len(positions)

                # 仓位以组合总资产为基准（现金+持仓按最近收盘估值）
                portfolio_value = capital
                for pcode, pos in positions.items():
                    pdf = daily_data.get(pcode)
                    if pdf is not None:
                        pc = self._last_close_up_to(pdf, date)
                        if pc is not None:
                            portfolio_value += pos['shares'] * pc

                bought = 0
                for _, row in buy_signals.iterrows():
                    if bought >= max_new:
                        break

                    code = row['code']
                    if code in positions or code not in daily_data:
                        continue

                    stock_df = daily_data[code]
                    day_data = stock_df[stock_df['date'] == date]
                    if len(day_data) == 0:
                        continue

                    # 检查涨停（开盘封死涨停买不进去）
                    open_price = day_data['open'].iloc[0]
                    prev_close = self._prev_close(stock_df, date)
                    if prev_close is None:
                        continue
                    limit_up = prev_close * (1 + self._limit_pct(code))

                    if open_price >= limit_up:
                        continue  # 涨停跳过

                    buy_price = min(open_price * (1 + self.slippage), limit_up)

                    # 计算仓位（信号强度决定仓位大小，基准=组合总资产）
                    signal_strength = abs(row.get('score', row['signal']))
                    shares = self.pos_manager.calc_position_size(
                        portfolio_value, buy_price, signal_strength, pos_config
                    )

                    if shares == 0:
                        continue

                    cost_amount = shares * buy_price
                    trade_cost = cost_amount * self.commission
                    if cost_amount + trade_cost > capital:
                        continue  # 现金不足

                    capital -= cost_amount + trade_cost

                    positions[code] = {
                        'shares': shares,
                        'cost': buy_price,
                        'buy_date': date,
                    }

                    trades.append({
                        'date': date, 'code': code, 'action': 'BUY',
                        'price': round(buy_price, 2), 'shares': shares,
                        'cost_basis': round(buy_price, 2),
                        'signal': round(row.get('score', row['signal']), 3),
                        'commission': round(trade_cost, 2)
                    })
                    bought += 1

            # === 4. 计算当日净值（T 收盘盯市，停牌沿用最近收盘）===
            total_value = capital
            for code, pos in positions.items():
                stock_df = daily_data.get(code)
                if stock_df is not None:
                    pc = self._last_close_up_to(stock_df, date)
                    if pc is not None:
                        total_value += pos['shares'] * pc

            equity_records.append({
                'date': date,
                'equity': round(total_value, 2),
                'cash': round(capital, 2),
                'positions': len(positions),
                'regime': regime_name,
                'position_pct': round((total_value - capital) / total_value * 100, 1)
            })

        # === 统计 ===
        equity_curve = pd.DataFrame(equity_records)
        trades_df = pd.DataFrame(trades)
        regime_df = pd.DataFrame(regime_history)
        stats = self._calc_stats(equity_curve, trades_df)

        return {
            'equity_curve': equity_curve,
            'trades': trades_df,
            'stats': stats,
            'regime_history': regime_df,
        }

    # ==================== 数据辅助 ====================

    @staticmethod
    def _limit_pct(code):
        """涨跌停幅度: 创业板(300/301)/科创板(688) 20%, 主板 10%"""
        return 0.2 if str(code).startswith(('300', '301', '688')) else 0.1

    @staticmethod
    def _prev_close(stock_df, date):
        """
        T 日的昨收基准（决策与涨跌停判断用, 必须早于 T 开盘）
        优先级: pre_close 列 → pctChg 反推 → 前一根K线收盘
        """
        day = stock_df[stock_df['date'] == date]
        if len(day) == 0:
            return None
        row = day.iloc[0]
        if 'pre_close' in stock_df.columns and pd.notna(row.get('pre_close')):
            return float(row['pre_close'])
        if 'pctChg' in stock_df.columns and pd.notna(row.get('pctChg')):
            pchg = float(row['pctChg'])
            if pchg != 0:
                return float(row['close']) / (1 + pchg / 100)
        prev = stock_df[stock_df['date'] < date]
        if len(prev) > 0:
            return float(prev['close'].iloc[-1])
        return None

    @staticmethod
    def _last_close_up_to(stock_df, date):
        """≤ date 最近一根K线的收盘价（估值盯市用, 停牌日沿用最近收盘而非归零）"""
        sub = stock_df[stock_df['date'] <= date]
        if len(sub) == 0:
            return None
        return float(sub['close'].iloc[-1])

    def _executable_sell_price(self, code, open_price, stock_df, date):
        """
        T 日开盘卖出的可执行价格
        开盘即封死跌停 → 无法成交 (False)；否则按开盘价-滑点, 且不跌破跌停价
        """
        prev_close = self._prev_close(stock_df, date)
        if prev_close is None:
            return open_price * (1 - self.slippage), True
        limit_down = prev_close * (1 - self._limit_pct(code))
        if open_price <= limit_down:
            return open_price, False
        return max(open_price * (1 - self.slippage), limit_down), True

    def _calc_stats(self, equity_curve, trades_df):
        """计算回测统计"""
        if len(equity_curve) == 0:
            return {}

        eq = equity_curve['equity']
        total_return = (eq.iloc[-1] / self.initial_capital - 1) * 100

        # 最大回撤
        peak = eq.expanding().max()
        drawdown = (eq - peak) / peak
        max_dd = drawdown.min() * 100

        # 日收益率
        daily_ret = eq.pct_change().dropna()
        sharpe = daily_ret.mean() / (daily_ret.std() + 1e-8) * np.sqrt(252) if len(daily_ret) > 1 else 0

        # 交易统计
        if len(trades_df) > 0 and 'pnl' in trades_df.columns:
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            win_trades = sell_trades[sell_trades['pnl'] > 0]
            lose_trades = sell_trades[sell_trades['pnl'] <= 0]

            win_rate = len(win_trades) / len(sell_trades) * 100 if len(sell_trades) > 0 else 0
            avg_win = win_trades['pnl'].mean() if len(win_trades) > 0 else 0
            avg_loss = lose_trades['pnl'].mean() if len(lose_trades) > 0 else 0

            # 盈亏比
            profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

            # 最大单笔亏损
            max_single_loss = sell_trades['pnl'].min() if len(sell_trades) > 0 else 0
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_loss_ratio = 0
            max_single_loss = 0

        return {
            '总收益率': f"{total_return:.2f}%",
            '最大回撤': f"{max_dd:.2f}%",
            '夏普比率': round(sharpe, 2),
            '初始资金': self.initial_capital,
            '期末资金': round(eq.iloc[-1], 2),
            '总交易次数': len(trades_df[trades_df['action'] == 'SELL']) if len(trades_df) > 0 else 0,
            '胜率': f"{win_rate:.1f}%",
            '平均盈利': round(avg_win, 2),
            '平均亏损': round(avg_loss, 2),
            '盈亏比': round(profit_loss_ratio, 2),
            '最大单笔亏损': round(max_single_loss, 2),
        }
