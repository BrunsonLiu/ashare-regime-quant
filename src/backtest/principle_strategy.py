# -*- coding: utf-8 -*-
"""
守则策略 —— 组装并验证(含真实成本)
=====================================
把已验证的三块组装成完整策略:
  1. 只玩行业龙头(龙头池)
  2. 只在 A 主线持有(环境择时)
  3. 低换手(龙头尽量不动, 只在环境切换/定期再平衡时调仓)

全部含真实成本: 佣金万2.5 + 印花税千0.5(卖) + 滑点千1。
关键对照: 同一策略在"含成本"与"零成本"下的差距 → 量化换手代价。

用法: python -m src.backtest.principle_strategy [--hold-n 10] [--rebalance monthly]
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.utils.market_env import MarketEnvironment, load_sentiment
from src.data_loader import DataLoader

COMMISSION = 0.00025
STAMP_TAX = 0.0005
SLIPPAGE = 0.001
START = '2023-09-08'


def load_prices(pool_file='stock_pool_leaders_pit.csv'):
    """默认用 PIT 龙头池(无前视); 排序用池内 past_amt_yi(PIT口径)"""
    loader = DataLoader()
    pool = pd.read_csv(os.path.join(DATA_DIR, pool_file), dtype={'code': str})
    pool['code'] = pool['code'].str.zfill(6)
    # 龙头排序: 用 PIT 成交额(仅回测前数据), 无则退回 avg_amount_yi
    for col in ('past_amt_yi', 'avg_amount_yi'):
        if col in pool.columns:
            pool = pool.sort_values(col, ascending=False)
            break
    codes = pool['code'].tolist()
    port = {}
    for c in codes:
        df = loader.load_cache(c)
        if df is None or len(df) < 100:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        port[c] = df.set_index('date')['close']
    prices = pd.DataFrame(port).sort_index()
    prices = prices.loc[prices.index >= pd.Timestamp(START)]
    ordered = [c for c in codes if c in prices.columns]
    return prices[ordered]


def env_series(index_df):
    idx = index_df.copy(); idx['date'] = pd.to_datetime(idx['date'])
    env_map, _ = MarketEnvironment().classify_series(idx, load_sentiment())
    return env_map


def select_holdings(prices, day, env, hold_n, mode='liquid'):
    """当日应持有的股票: 在该日有价、按龙头优先级取前 hold_n 只; hold_n<=0 表示全部"""
    avail = list(prices.columns[prices.loc[day].notna()])
    if not avail:
        return []
    if hold_n <= 0:
        return avail
    return avail[:hold_n]


def backtest(prices, envs, hold_envs, hold_n, rebalance, cost=True):
    """
    组合模拟:
    - 在 hold_envs 中的环境持有 hold_n 只(等权), 否则空仓
    - 再平衡: 'env'=仅环境切换时调仓; 'monthly'=每月首个交易日调仓
    """
    dates = prices.index
    env_arr = pd.Series(envs).reindex(dates).ffill()
    cash = 1.0            # 归一化净值
    holdings = {}         # {code: shares_value_frac} 用份额比例简化
    equity = []
    prev_month = None
    n_trades = 0

    for i, day in enumerate(dates):
        in_market = env_arr.iloc[i] in hold_envs
        # 是否调仓
        do_rebal = False
        if i == 0:
            do_rebal = True
        else:
            prev_in = env_arr.iloc[i-1] in hold_envs
            if rebalance == 'env' and in_market != prev_in:
                do_rebal = True
            elif rebalance == 'monthly':
                cur_m = (day.year, day.month)
                if prev_month is not None and cur_m != prev_month:
                    do_rebal = True
        prev_month = (day.year, day.month)

        if do_rebal:
            # 计算当前总资产(持仓按当日价)
            total = cash
            for code, sh in holdings.items():
                px = prices.loc[day].get(code)
                if pd.notna(px):
                    total += sh * px
            # 目标持仓
            if in_market:
                picks = select_holdings(prices, day, env_arr.iloc[i], hold_n, 'liquid')
                if picks:
                    target_per = total / len(picks)
                    new_holdings = {}
                    # 卖出不在目标里的
                    for code, sh in holdings.items():
                        if code not in picks:
                            px = prices.loc[day].get(code)
                            if pd.notna(px):
                                proceeds = sh * px
                                fee = proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE if cost else 0)
                                cash += proceeds - fee
                                n_trades += 1
                            new_holdings.pop(code, None)
                    # 买入/调整目标
                    cost_sum = cash
                    for code in picks:
                        px = prices.loc[day].get(code)
                        if pd.isna(px) or px <= 0:
                            continue
                        buy_fee_rate = (COMMISSION + SLIPPAGE) if cost else 0
                        # 目标市值 target_per, 现有该股市值
                        cur_sh = holdings.get(code, 0.0)
                        cur_val = cur_sh * px
                        delta_val = target_per - cur_val
                        if abs(delta_val) < target_per * 0.1:  # 偏离<目标仓位10%则不动(阈值随仓位数缩放)
                            new_holdings[code] = cur_sh
                            continue
                        if delta_val > 0:
                            afford = min(delta_val, max(cash, 0))
                            if afford > 0:
                                sh = afford / px / (1 + buy_fee_rate)
                                fee = sh * px * buy_fee_rate
                                cash -= (sh * px + fee)
                                new_holdings[code] = cur_sh + sh
                                n_trades += 1
                            else:
                                new_holdings[code] = cur_sh
                        else:
                            sell_val = min(-delta_val, cur_val)
                            sh = sell_val / px
                            proceeds = sh * px
                            fee = proceeds * ((COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                            cash += proceeds - fee
                            new_holdings[code] = cur_sh - sh
                            n_trades += 1
                    holdings = {k: v for k, v in new_holdings.items() if v > 1e-9}
                else:
                    # 无可用标的 → 全部清仓
                    for code, sh in list(holdings.items()):
                        px = prices.loc[day].get(code)
                        if pd.notna(px):
                            proceeds = sh * px
                            fee = proceeds * ((COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                            cash += proceeds - fee
                    holdings = {}
            else:
                # 环境不允许持有 → 清仓
                for code, sh in list(holdings.items()):
                    px = prices.loc[day].get(code)
                    if pd.notna(px):
                        proceeds = sh * px
                        fee = proceeds * ((COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                        cash += proceeds - fee
                        n_trades += 1
                holdings = {}

        # 盯市
        total = cash
        for code, sh in holdings.items():
            px = prices.loc[day].get(code)
            if pd.notna(px):
                total += sh * px
        equity.append({'date': day, 'equity': total})

    eq = pd.DataFrame(equity).set_index('date')['equity']
    total_ret = eq.iloc[-1] - 1
    peak = eq.cummax()
    dd = ((eq / peak) - 1).min()
    return {'ret_pct': round(total_ret * 100, 1), 'max_dd_pct': round(dd * 100, 1),
            'n_trades': n_trades, 'equity': eq}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--hold-n', type=int, default=10, help='持有龙头数量(0=全部239只)')
    ap.add_argument('--rebalance', choices=['env', 'monthly'], default='env')
    args = ap.parse_args()

    prices = load_prices()
    loader = DataLoader()
    envs = env_series(loader.get_index_data('000001', days=1300))
    print(f'龙头池 {prices.shape[1]} 只, {len(prices)} 交易日')

    # 买入持有基准
    bh_rets = prices.pct_change(fill_method=None).mean(axis=1)
    bh_eq = (1 + bh_rets.fillna(0)).cumprod()
    bh_ret = (bh_eq.iloc[-1] - 1) * 100
    bh_dd = ((bh_eq / bh_eq.cummax()) - 1).min() * 100

    norm = {0: '全部'}
    rows = []
    for hold_n, mode in [(0, '全池239只'), (args.hold_n, f'前{args.hold_n}只'), (5, '前5只(守则上限)')]:
        for rebal in ['env', 'monthly']:
            for cost in [True, False]:
                st = backtest(prices, envs, {'A'}, hold_n, rebal, cost=cost)
                rows.append({'持仓': mode, '再平衡': rebal, '成本': '含' if cost else '零',
                             '收益%': st['ret_pct'], '回撤%': st['max_dd_pct'], '交易': st['n_trades']})

    print(f'\n买入持有基准: 收益{bh_ret:+.1f}%  回撤{bh_dd:.1f}%')
    print('\n=== 守则策略: 只在A主线持有 × 持仓数 × 再平衡 × 成本 ===')
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))

    out_dir = os.path.join(DATA_DIR, 'experiments')
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f'principle_{pd.Timestamp.now():%Y%m%d_%H%M}.csv')
    df.to_csv(p, index=False, encoding='utf-8-sig')
    print(f'\n[OK] → {p}')


if __name__ == '__main__':
    main()
