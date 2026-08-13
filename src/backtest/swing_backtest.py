"""
swing_backtest.py - 中长线埋伏回测引擎

核心逻辑（散户埋伏，非因子轮动）：
  只在"缩量横盘企稳"的低位上游票里埋伏，拿中线。
  频率低、换手少、依赖产业链催化而非每日信号。

与短线引擎的区别：
  - 买入：只在 detect_low_position 判定 eligible 时买入（左侧缩量低吸 / 右侧放量确认）
  - 卖出：止盈35% / 时间止损60天 / 跌破横盘下沿 / 移动止盈
  - 不天天换仓，默认持有

回测假设（保守）：
  - T+1：当天检测到信号，次日开盘买入
  - 涨跌停：涨停买不进（跳过），跌停卖不出（次日再试）
  - 费用：佣金万2.5 + 印花税千0.5 + 滑点千1
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import TRADE_CONFIG, DAILY_DIR
from src.sentiment.lurk_detector import LurkDetector
from src.sentiment.supply_chain import get_all_upstream_stocks, get_theme_by_code


class SwingBacktestEngine:
    """中长线埋伏回测引擎"""

    def __init__(self, config: Dict = None):
        self.cfg = config or {}
        self.initial_capital = self.cfg.get("initial_capital", TRADE_CONFIG["initial_capital"])
        self.commission = TRADE_CONFIG["commission_rate"]
        self.stamp_tax = TRADE_CONFIG["stamp_tax"]
        self.slippage = TRADE_CONFIG["slippage"]

        # 中线专用仓位
        self.max_positions = self.cfg.get("max_positions", 3)     # 中线最多3只
        self.position_pct = self.cfg.get("position_pct", 0.15)    # 单只15%
        self.single_max_pct = self.cfg.get("single_max_pct", 0.25)  # 单只上限25%

        self.detector = LurkDetector()

        # 触发买入的信号
        self.buy_on_left = self.cfg.get("buy_on_left", True)    # 允许左侧缩量低吸
        self.buy_on_right = self.cfg.get("buy_on_right", True)  # 允许右侧放量确认
        self.min_score = self.cfg.get("min_score", 8)           # 最低埋伏评分

    def run(self, daily_data: Dict[str, pd.DataFrame],
            index_df: pd.DataFrame = None,
            board_filter=("60", "00")) -> Dict:
        """
        运行中线埋伏回测

        参数:
            daily_data: {code: DataFrame[date, open, high, low, close, volume, ...]}
            index_df: 指数数据（可选，用于交易日历）
            board_filter: 股票板块过滤（默认主板）

        返回: dict {equity_curve, trades, stats}
        """
        # 上游标的池
        upstream = get_all_upstream_stocks(board_filter)
        upstream_codes = [s["code"] for s in upstream if s["code"] in daily_data]
        # 名称映射
        name_map = {s["code"]: s["name"] for s in upstream if s["code"] in daily_data}

        # 交易日历（用上证指数或任一股票的日期）
        if index_df is not None and 'date' in index_df.columns and len(index_df) > 0:
            all_dates = sorted(index_df['date'].unique())
        else:
            # 用上游票里最长的日期序列
            all_dates = sorted(set().union(*[set(daily_data[c]['date']) for c in upstream_codes])) if upstream_codes else []
            all_dates = [d for d in all_dates if hasattr(d, 'strftime') or isinstance(d, str)]

        capital = self.initial_capital
        positions = {}  # {code: {shares, cost, buy_date, stop_price, peak}}
        trades = []
        equity_records = []

        # 预计算每只票的每日数据（按日期索引，加速查找）
        stock_data = {}
        for code in upstream_codes:
            df = daily_data[code].copy()
            df = df.sort_values('date').reset_index(drop=True)
            df['date_str'] = df['date'].astype(str)
            stock_data[code] = df

        # 逐日回测
        for i, date in enumerate(all_dates):
            date_str = str(date)[:10]

            # ============ 1. 处理卖出（先卖）============
            for code in list(positions.keys()):
                pos = positions[code]
                df = stock_data.get(code)
                if df is None:
                    continue

                day_data = df[df['date_str'] == date_str]
                if len(day_data) == 0:
                    continue

                current_price = day_data['close'].iloc[0]
                open_price = day_data['open'].iloc[0]

                # 持有天数
                buy_date = pos['buy_date']
                days_held = self._days_between(buy_date, date_str)

                # 更新峰值（移动止盈用）
                pos['peak'] = max(pos.get('peak', pos['cost']), current_price)

                # 卖出判断
                should_sell, reason = self.detector.check_swing_exit(pos, current_price, days_held)

                # T+1：买入当天不能卖
                if should_sell and buy_date == date_str:
                    should_sell = False

                if should_sell:
                    # 跌停卖不出
                    pre_close = day_data['pre_close'].iloc[0] if 'pre_close' in day_data.columns else open_price
                    if current_price <= pre_close * 0.9:
                        trades.append({
                            'date': date_str, 'code': code, 'action': 'SELL_FAIL',
                            'price': current_price, 'shares': pos['shares'],
                            'reason': '跌停无法卖出', 'pnl': 0
                        })
                        continue

                    sell_price = open_price * (1 - self.slippage)
                    shares = pos['shares']
                    cost = pos['cost']
                    proceeds = shares * sell_price
                    trade_cost = proceeds * (self.commission + self.stamp_tax)
                    pnl = shares * (sell_price - cost) - trade_cost
                    capital += proceeds - trade_cost

                    trades.append({
                        'date': date_str, 'code': code, 'action': 'SELL',
                        'price': round(sell_price, 2), 'shares': shares,
                        'cost_basis': round(cost, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round((sell_price / cost - 1) * 100, 2),
                        'reason': reason,
                        'name': name_map.get(code, ''),
                        'commission': round(trade_cost, 2)
                    })
                    del positions[code]

            # ============ 2. 处理买入 ============
            if len(positions) < self.max_positions:
                for code in upstream_codes:
                    if len(positions) >= self.max_positions:
                        break
                    if code in positions:
                        continue

                    df = stock_data[code]
                    # 只用到当前日期的数据做检测（避免未来函数）
                    df_up_to = df[df['date_str'] <= date_str]
                    if len(df_up_to) < 60:
                        continue

                    # 检测埋伏信号（用当日及之前的数据）
                    r = self.detector.detect_low_position(code, name_map.get(code, code), df_up_to)

                    # 判定是否买入
                    if not r["eligible"] or r["score"] < self.min_score:
                        continue

                    # 买入方式过滤
                    if r["buy_mode"] == "left" and not self.buy_on_left:
                        continue
                    if r["buy_mode"] == "right" and not self.buy_on_right:
                        continue
                    if r["buy_mode"] == "none":
                        continue

                    # T+1：信号当日不买，次日开盘买（这里 date 已是次日，因为检测用的 df_up_to 含当日）
                    # 实际：检测到信号的下一天买入
                    # 简化：当前 date 就是买入日（检测时 df_up_to 已含当天收盘，次日开盘买）
                    day_data = df[df['date_str'] == date_str]
                    if len(day_data) == 0:
                        continue
                    open_price = day_data['open'].iloc[0]
                    pre_close = day_data['pre_close'].iloc[0] if 'pre_close' in day_data.columns else open_price

                    # 涨停买不进
                    if open_price >= pre_close * 1.1:
                        continue

                    buy_price = open_price * (1 + self.slippage)

                    # 仓位
                    target_value = min(capital * self.position_pct, capital * self.single_max_pct)
                    shares = int(target_value / buy_price / 100) * 100
                    if shares == 0:
                        continue

                    cost_amount = shares * buy_price
                    trade_cost = cost_amount * self.commission
                    if cost_amount + trade_cost > capital:
                        continue

                    capital -= cost_amount + trade_cost
                    positions[code] = {
                        'shares': shares,
                        'cost': buy_price,
                        'buy_date': date_str,
                        'stop_price': r["stop_price"],
                        'peak': buy_price,
                        'buy_mode': r["buy_mode"],
                        'score': r["score"],
                    }

                    trades.append({
                        'date': date_str, 'code': code, 'action': 'BUY',
                        'price': round(buy_price, 2), 'shares': shares,
                        'cost_basis': round(buy_price, 2),
                        'reason': f"埋伏{r['buy_mode']}(评分{r['score']})",
                        'name': name_map.get(code, ''),
                        'commission': round(trade_cost, 2)
                    })

            # ============ 3. 计算净值 ============
            total_value = capital
            for code, pos in positions.items():
                df = stock_data.get(code)
                if df is not None:
                    day_data = df[df['date_str'] == date_str]
                    if len(day_data) > 0:
                        total_value += pos['shares'] * day_data['close'].iloc[0]

            equity_records.append({
                'date': date_str,
                'equity': round(total_value, 2),
                'cash': round(capital, 2),
                'positions': len(positions),
            })

        # ============ 统计 ============
        equity_curve = pd.DataFrame(equity_records)
        trades_df = pd.DataFrame(trades)
        stats = self._calc_stats(equity_curve, trades_df)

        return {
            'equity_curve': equity_curve,
            'trades': trades_df,
            'stats': stats,
        }

    def _days_between(self, d1: str, d2: str) -> int:
        """计算两个日期字符串之间的天数"""
        try:
            dt1 = datetime.strptime(d1[:10], "%Y-%m-%d")
            dt2 = datetime.strptime(d2[:10], "%Y-%m-%d")
            return (dt2 - dt1).days
        except Exception:
            return 0

    def _calc_stats(self, equity_curve, trades_df):
        """统计指标"""
        if len(equity_curve) == 0:
            return {}

        eq = equity_curve['equity']
        total_return = (eq.iloc[-1] / self.initial_capital - 1) * 100

        peak = eq.expanding().max()
        drawdown = (eq - peak) / peak
        max_dd = drawdown.min() * 100

        daily_ret = eq.pct_change().dropna()
        sharpe = daily_ret.mean() / (daily_ret.std() + 1e-8) * np.sqrt(252) if len(daily_ret) > 1 else 0

        if len(trades_df) > 0 and 'pnl' in trades_df.columns:
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            win_trades = sell_trades[sell_trades['pnl'] > 0]
            lose_trades = sell_trades[sell_trades['pnl'] <= 0]
            win_rate = len(win_trades) / len(sell_trades) * 100 if len(sell_trades) > 0 else 0
            avg_win = win_trades['pnl'].mean() if len(win_trades) > 0 else 0
            avg_loss = lose_trades['pnl'].mean() if len(lose_trades) > 0 else 0
            profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            max_single_loss = sell_trades['pnl'].min() if len(sell_trades) > 0 else 0
            # 平均持有天数
            if len(sell_trades) > 0:
                avg_hold = sell_trades.apply(
                    lambda r: self._days_between(r['date'], r['date']), axis=1).mean()
        else:
            win_rate = avg_win = avg_loss = profit_loss_ratio = max_single_loss = 0

        return {
            '总收益率': f"{total_return:.2f}%",
            '最大回撤': f"{max_dd:.2f}%",
            '夏普比率': round(sharpe, 2),
            '初始资金': self.initial_capital,
            '期末资金': round(eq.iloc[-1], 2),
            '总交易次数': len(trades_df[trades_df['action'] == 'SELL']) if len(trades_df) > 0 else 0,
            '买入次数': len(trades_df[trades_df['action'] == 'BUY']) if len(trades_df) > 0 else 0,
            '胜率': f"{win_rate:.1f}%",
            '平均盈利': round(avg_win, 2),
            '平均亏损': round(avg_loss, 2),
            '盈亏比': round(profit_loss_ratio, 2),
            '最大单笔亏损': round(max_single_loss, 2),
        }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # 加载上游票数据
    from src.data_loader import DataLoader
    from src.sentiment.supply_chain import get_all_upstream_stocks

    loader = DataLoader()
    upstream = get_all_upstream_stocks(("60", "00"))
    codes = [s["code"] for s in upstream]

    print(f"加载 {len(codes)} 只上游标的的日线数据...")
    daily_data = {}
    for code in codes:
        df = loader.load_cache(code)
        if df is not None and len(df) > 0:
            daily_data[code] = df

    print(f"成功加载 {len(daily_data)} 只")

    # 上证指数（交易日历）
    index_df = loader.get_index_data("000001", days=300)

    engine = SwingBacktestEngine()
    result = engine.run(daily_data, index_df)

    print("\n=== 中线埋伏回测结果 ===")
    for k, v in result['stats'].items():
        print(f"  {k}: {v}")

    if len(result['trades']) > 0:
        print(f"\n=== 交易明细（{len(result['trades'])}笔）===")
        trades = result['trades']
        for _, t in trades.iterrows():
            act = t['action']
            nm = t.get('name', '')
            pnl = t.get('pnl', '')
            rsn = t.get('reason', '')
            if act == 'BUY':
                print(f"  {t['date']} BUY  {t['code']} {nm} @{t['price']}  {rsn}")
            else:
                print(f"  {t['date']} {act} {t['code']} {nm} @{t['price']} pnl={pnl}  {rsn}")
