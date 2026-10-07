# -*- coding: utf-8 -*-
"""
行业情绪热度 —— 用情绪数据识别"主线"(守则本意)
================================================
守则2.4: 板块内涨停家数≥3 → 板块有热度; 连续在前列 → 主线确认。
本模块: 由 zt_events(涨停事件) join 行业分类, 算每日各行业涨停家数/连板高度,
识别"正在凝聚的行业"(情绪主线) —— 与价格动量(追高)相反。

严格无前视: 判 T 日主线用 T-1 及之前的涨停数据。

用法: python -m src.backtest.sentiment_sector [--top-industries 1] [--hold-k 3]
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


def build_industry_heat():
    """每日×行业: 涨停家数, 最高连板; 由 zt_events + 行业分类 join"""
    zt = pd.read_csv(os.path.join(DATA_DIR, 'zt_events.csv'), header=None,
                     names=['date', 'code', 'lianban'], dtype={'code': str})
    zt['code'] = zt['code'].str.zfill(6)
    zt['date'] = pd.to_datetime(zt['date'])

    loader = DataLoader()
    ind = loader.get_industry()[['code_std', 'industry']].rename(columns={'code_std': 'code'})
    ind['code'] = ind['code'].astype(str).str.zfill(6)
    ind = ind.drop_duplicates('code')

    zt = zt.merge(ind, on='code', how='left')
    heat = zt.groupby(['date', 'industry']).agg(
        zt_cnt=('code', 'size'), max_lb=('lianban', 'max')).reset_index()
    return heat


def industry_heat_series(heat, day, lookback=5):
    """截至 day(含)的各行业近 lookback 日涨停热度: 家数合计 + 连板高度"""
    hist = heat[(heat['date'] <= day) & (heat['date'] > day - pd.Timedelta(days=lookback * 2))]
    if len(hist) == 0:
        return {}
    agg = hist.groupby('industry').agg(zt=('zt_cnt', 'sum'), lb=('max_lb', 'max'))
    # 热度分 = 涨停家数 + 连板高度*3 (有持续性的高标才算主线)
    return (agg['zt'] + agg['lb'] * 3).to_dict()


def backtest(prices, ind_map, envs, heat, top_industries=1, hold_k=3,
             rebalance_days=10, cost=True, only_env_A=True, lookback=5,
             cutoff=None, cooldown=10):
    """cutoff: 组合回撤熔断阈值(如-0.08, 守则第五章); None=不启用
    cooldown: 熔断后冷却交易日数"""
    prices_val = prices.ffill()
    dates = prices.index
    env_arr = pd.Series(envs).reindex(dates).ffill()
    cash, holdings, equity = 1.0, {}, []
    n_trades = 0
    next_rebal = 0
    peak = 1.0
    cooldown_left = 0

    def pv(day):
        return cash + sum(sh * prices_val.loc[day].get(c, 0)
                          for c, sh in holdings.items()
                          if pd.notna(prices_val.loc[day].get(c)))

    for i, day in enumerate(dates):
        # 组合回撤熔断(守则: -8%清仓+冷却)
        if cutoff is not None:
            cur = pv(day)
            peak = max(peak, cur)
            if cooldown_left > 0:
                cooldown_left -= 1
            elif (cur - peak) / peak <= cutoff:
                # 熔断: 清仓
                for c in list(holdings):
                    px = prices.loc[day].get(c)
                    if pd.notna(px):
                        proceeds = holdings[c] * px
                        cash += proceeds - (proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                        n_trades += 1
                        del holdings[c]
                cooldown_left = cooldown
                peak = cur  # 回合制: 以当前净值为新基准(避免永久锁死)

        in_market = (env_arr.iloc[i] == 'A') if only_env_A else True
        if cooldown_left > 0:
            in_market = False  # 冷却期空仓
        if i >= next_rebal:
            next_rebal = i + rebalance_days
            total = pv(day)
            targets = []
            if in_market:
                prev_day = dates[i - 1] if i > 0 else day
                hm = industry_heat_series(heat, prev_day, lookback)
                if hm:
                    top = sorted(hm.items(), key=lambda x: -x[1])[:top_industries]
                    top_inds = {k for k, _ in top if _ > 0}
                    smom = (prices.loc[:day].iloc[-1] / prices.loc[:day].iloc[-period] - 1).dropna() \
                        if len(prices.loc[:day]) > period else pd.Series(dtype=float)
                    cand = [(c, smom.get(c, -9)) for c in prices.columns
                            if ind_map.get(c) in top_inds and c in smom.index]
                    cand.sort(key=lambda x: -x[1])
                    targets = [c for c, _ in cand[:hold_k * top_industries]]
            for c in list(holdings):
                if c not in targets:
                    px = prices.loc[day].get(c)
                    if pd.notna(px):
                        proceeds = holdings[c] * px
                        cash += proceeds - (proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                        n_trades += 1
                        del holdings[c]
            if targets:
                tgt_val = total / len(targets)
                for c in targets:
                    px = prices.loc[day].get(c)
                    if pd.isna(px) or px <= 0:
                        continue
                    cur_h = holdings.get(c, 0.0)
                    delta = tgt_val - cur_h * px
                    if delta <= 0:
                        continue
                    afford = min(delta, max(cash, 0))
                    if afford > 0:
                        fr = (COMMISSION + SLIPPAGE) if cost else 0
                        sh = afford / px / (1 + fr)
                        cash -= sh * px * (1 + fr)
                        holdings[c] = cur_h + sh
                        n_trades += 1
        equity.append({'date': day, 'equity': pv(day)})

    eq = pd.DataFrame(equity).set_index('date')['equity']
    peak_s = eq.cummax()
    return {'ret_pct': round((eq.iloc[-1] - 1) * 100, 1),
            'max_dd_pct': round(((eq / peak_s) - 1).min() * 100, 1),
            'n_trades': n_trades, 'equity': eq}


period = 20  # 个股动量回看(仅用于板块内排序, 非选板块)


def load_prices_ind():
    loader = DataLoader()
    pool = pd.read_csv(os.path.join(DATA_DIR, 'stock_pool_leaders_pit.csv'), dtype={'code': str})
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
    return prices.loc[prices.index >= pd.Timestamp(START)], ind_map


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--top-industries', type=int, default=1)
    ap.add_argument('--hold-k', type=int, default=3)
    ap.add_argument('--rebal-days', type=int, default=10)
    args = ap.parse_args()

    prices, ind_map = load_prices_ind()
    loader = DataLoader()
    idx = loader.get_index_data('000001', days=1300); idx['date'] = pd.to_datetime(idx['date'])
    env_map, _ = MarketEnvironment().classify_series(idx, load_sentiment())
    heat = build_industry_heat()
    print(f'PIT龙头池 {prices.shape[1]}只, 涨停热 行业数={heat["industry"].nunique()}')

    print('\n=== 情绪主线轮动(用涨停热度选行业, 只在A环境) ===')
    rows = []
    for ti in (1, 3):
        for k in (1, 3, 5):
            for cost in (True, False):
                st = backtest(prices, ind_map, env_map, heat, ti, k,
                              rebalance_days=args.rebal_days, cost=cost)
                rows.append({'前N行业': ti, '每行业持仓': k, '成本': '含' if cost else '零',
                             '收益%': st['ret_pct'], '回撤%': st['max_dd_pct'], '交易': st['n_trades']})
    print(pd.DataFrame(rows).to_string(index=False))

    # 加守则回撤熔断(-8%清仓+冷却10日)
    print('\n=== 加守则组合熔断(-8%清仓+10日冷却) ===')
    rows2 = []
    for ti in (1, 3):
        for k in (1, 3, 5):
            st = backtest(prices, ind_map, env_map, heat, ti, k,
                          rebalance_days=args.rebal_days, cost=True, cutoff=-0.08, cooldown=10)
            rows2.append({'前N行业': ti, '每行业持仓': k,
                          '收益%': st['ret_pct'], '回撤%': st['max_dd_pct'], '交易': st['n_trades']})
    print(pd.DataFrame(rows2).to_string(index=False))

    # 对照: 只在A持有整个龙头池
    bh = prices.pct_change(fill_method=None).mean(axis=1)
    env_a = pd.Series(env_map).reindex(prices.index).ffill() == 'A'
    eq_a = (1 + bh.where(env_a, 0).fillna(0)).cumprod()
    print(f'\n对照-只在A持有整个龙头池: 收益{(eq_a.iloc[-1]-1)*100:+.1f}% '
          f'回撤{((eq_a/eq_a.cummax())-1).min()*100:.1f}%')


if __name__ == '__main__':
    main()
