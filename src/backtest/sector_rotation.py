# -*- coding: utf-8 -*-
"""
主线板块轮动 —— 守则"选主线板块中的龙头"的落地
================================================
守则2.4看板块: 涨幅前列且持续的板块=主线; 2.2选股: 主线板块中的龙头。
本模块: 每个调仓日, 按行业成分股近期动量找最强板块 → 只买该板块的龙头。

严格无前视:
- 行业动量用 T-1 及之前的收益
- 龙头池用 PIT 口径(回测起点前选)
- 成交按 T 日开盘? 这里简化为按收盘(组合级) —— 注明
- 环境过滤: 只在 A 主线持有(否则空仓)

用法: python -m src.backtest.sector_rotation [--top-sectors 1] [--hold-k 3] [--mom-days 20]
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

COMMISSION, STAMP_TAX, SLIPPAGE = 0.00025, 0.0005, 0.001
START = '2023-09-08'


def load_universe(pool_file='stock_pool_leaders_pit.csv'):
    """返回 (价格矩阵, 行业映射)"""
    loader = DataLoader()
    pool = pd.read_csv(os.path.join(DATA_DIR, pool_file), dtype={'code': str})
    pool['code'] = pool['code'].str.zfill(6)
    ind_map = dict(zip(pool['code'], pool['industry']))
    port = {}
    for c in pool['code']:
        df = loader.load_cache(c)
        if df is None or len(df) < 100:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        port[c] = df.set_index('date')['close']
    prices = pd.DataFrame(port).sort_index()
    prices = prices.loc[prices.index >= pd.Timestamp(START)]
    return prices, ind_map


def industry_momentum(prices, ind_map, day, mom_days):
    """各行业动量 = 成分股过去 mom_days 收益均值(只用 <day 数据)"""
    hist = prices.loc[:day]
    if len(hist) < mom_days + 1:
        return {}
    p0 = hist.iloc[-mom_days - 1]
    p1 = hist.iloc[-1]
    rets = (p1 / p0 - 1).dropna()
    by_ind = {}
    for code, r in rets.items():
        ind = ind_map.get(code)
        if ind:
            by_ind.setdefault(ind, []).append(r)
    return {ind: float(np.mean(v)) for ind, v in by_ind.items() if len(v) >= 2}


def stock_momentum(prices, day, mom_days):
    hist = prices.loc[:day]
    if len(hist) < mom_days + 1:
        return pd.Series(dtype=float)
    return (hist.iloc[-1] / hist.iloc[-mom_days - 1] - 1).dropna()


def backtest(prices, ind_map, envs, top_sectors=1, hold_k=3, mom_days=20,
             rebalance_days=20, cost=True, only_env_A=True):
    """每 rebalance_days 调仓; 选 top_sectors 个最强板块, 各取动量前 hold_k 只龙头

    估值用 prices_val(前向填充): 持仓股当日无价(停牌)时沿用最近收盘,
    否则会把整个持仓丢弃导致净值塌方(engine 同类 bug 的翻版);
    交易仍用 prices(当日真实价, 停牌不可成交)。
    """
    prices_val = prices.ffill()
    dates = prices.index
    env_arr = pd.Series(envs).reindex(dates).ffill()
    cash, holdings, equity = 1.0, {}, []
    n_trades = 0
    next_rebal = 0

    def portfolio_value(day):
        total = cash
        for c, sh in holdings.items():
            px = prices_val.loc[day].get(c)
            if pd.notna(px):
                total += sh * px
        return total

    for i, day in enumerate(dates):
        in_market = (env_arr.iloc[i] == 'A') if only_env_A else True
        do_rebal = (i >= next_rebal)
        if do_rebal:
            next_rebal = i + rebalance_days
            total = portfolio_value(day)
            targets = []
            if in_market:
                mom_ind = industry_momentum(prices, ind_map, day, mom_days)
                if mom_ind:
                    top = sorted(mom_ind.items(), key=lambda x: -x[1])[:top_sectors]
                    top_inds = {k for k, _ in top}
                    smom = stock_momentum(prices, day, mom_days)
                    cand = [(c, smom.get(c, -9)) for c in prices.columns
                            if ind_map.get(c) in top_inds and c in smom.index]
                    cand.sort(key=lambda x: -x[1])
                    targets = [c for c, _ in cand[:hold_k * top_sectors]]
            # 清掉不在targets的(按当日真实价成交, 停牌则跳过)
            for c in list(holdings):
                if c not in targets:
                    px = prices.loc[day].get(c)
                    if pd.notna(px):
                        proceeds = holdings[c] * px
                        cash += proceeds - (proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                        n_trades += 1
                        del holdings[c]
            # 买入targets等权
            if targets:
                tgt_val = total / len(targets)
                for c in targets:
                    px = prices.loc[day].get(c)
                    if pd.isna(px) or px <= 0:
                        continue
                    cur = holdings.get(c, 0.0)
                    delta = tgt_val - cur * px
                    if delta <= 0:
                        continue
                    afford = min(delta, max(cash, 0))
                    if afford > 0:
                        fee_rate = (COMMISSION + SLIPPAGE) if cost else 0
                        sh = afford / px / (1 + fee_rate)
                        cash -= sh * px * (1 + fee_rate)
                        holdings[c] = cur + sh
                        n_trades += 1
        equity.append({'date': day, 'equity': portfolio_value(day)})

    eq = pd.DataFrame(equity).set_index('date')['equity']
    peak = eq.cummax()
    return {'ret_pct': round((eq.iloc[-1] - 1) * 100, 1),
            'max_dd_pct': round(((eq / peak) - 1).min() * 100, 1),
            'n_trades': n_trades, 'equity': eq}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--top-sectors', type=int, default=1)
    ap.add_argument('--hold-k', type=int, default=3)
    ap.add_argument('--mom-days', type=int, default=20)
    ap.add_argument('--rebal-days', type=int, default=20)
    args = ap.parse_args()

    prices, ind_map = load_universe()
    loader = DataLoader()
    idx = loader.get_index_data('000001', days=1300); idx['date'] = pd.to_datetime(idx['date'])
    env_map, _ = MarketEnvironment().classify_series(idx, load_sentiment())
    print(f'PIT龙头池 {prices.shape[1]}只 / {len(set(ind_map.values()))}行业, {len(prices)}交易日')

    bh = prices.pct_change(fill_method=None).mean(axis=1)
    bh_eq = (1 + bh.fillna(0)).cumprod()
    print(f'基准-龙头池等权持有: 收益{(bh_eq.iloc[-1]-1)*100:+.1f}%  '
          f'回撤{((bh_eq/bh_eq.cummax())-1).min()*100:.1f}%')

    rows = []
    for ts in (1, 3):
        for k in (1, 3, 5):
            for cost in (True, False):
                st = backtest(prices, ind_map, env_map, top_sectors=ts, hold_k=k,
                              mom_days=args.mom_days, rebalance_days=args.rebal_days, cost=cost)
                rows.append({'前N板块': ts, '每板块持仓': k, '成本': '含' if cost else '零',
                             '收益%': st['ret_pct'], '回撤%': st['max_dd_pct'], '交易': st['n_trades']})
    df = pd.DataFrame(rows)
    print('\n=== 主线板块轮动(只在A环境, 月度调仓) ===')
    print(df.to_string(index=False))

    out = os.path.join(DATA_DIR, 'experiments', f'sector_rotation_{pd.Timestamp.now():%Y%m%d_%H%M}.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f'\n[OK] → {out}')


if __name__ == '__main__':
    main()
