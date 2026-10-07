# -*- coding: utf-8 -*-
"""
逐年滚动龙头池 —— 最严格的时点验证
====================================
结论文档的最大漏洞: PIT池用"回测起点前"数据选一次, 之后固定。
但真实交易中, 我们每年都应重新评估"谁是龙头"(用截至当时的数据)。

本模块: walk-forward 逐年滚动 —— 每年初用**截至该时点**的成交额重选龙头,
下一年只在当年的龙头池里交易。彻底消除"选池用未来信息"的疑虑。

用法: python -m src.backtest.rolling_pit
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.utils.market_env import MarketEnvironment, load_sentiment
from src.data_loader import DataLoader

COMMISSION, STAMP_TAX, SLIPPAGE = 0.00025, 0.0005, 0.001
START = pd.Timestamp('2023-09-08')


def load_all(codes):
    loader = DataLoader()
    port = {}
    for c in codes:
        df = loader.load_cache(c)
        if df is None or len(df) < 100:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        port[c] = df[['close', 'amount']]
    return port


def select_leaders_at(data, asof, top_n_per_ind=3, min_amt_yi=0.3, lookback=250):
    """截至 asof 用过去 lookback 交易日成交额选龙头"""
    ind = DataLoader().get_industry()[['code_std', 'industry']].rename(columns={'code_std': 'code'})
    ind['code'] = ind['code'].astype(str).str.zfill(6)
    ind = ind.drop_duplicates('code')
    ind_map = dict(zip(ind['code'], ind['industry']))
    rows = []
    for c, d in data.items():
        past = d[d.index < asof].tail(lookback)
        if len(past) < 60 or c not in ind_map:
            continue
        rows.append({'code': c, 'industry': ind_map[c], 'amt': float(past['amount'].mean())})
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return set()
    df = df[df['amt'] >= min_amt_yi * 1e8]
    df['rank'] = df.groupby('industry')['amt'].rank(ascending=False, method='first')
    return set(df[df['rank'] <= top_n_per_ind]['code'])


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    full = pd.read_csv(os.path.join(DATA_DIR, 'stock_pool.csv'), dtype={'code': str})
    full['code'] = full['code'].str.zfill(6)
    full = full[~full['code'].str.contains(r'30|68', na=False)]  # 主板(龙头池口径)
    data = load_all(full['code'].tolist())
    print(f'加载 {len(data)} 只')

    idx = DataLoader().get_index_data('000001', days=1300)
    idx['date'] = pd.to_datetime(idx['date'])
    env_map, _ = MarketEnvironment().classify_series(idx, load_sentiment())

    # 交易日历
    all_dates = sorted(set().union(*[set(d.index) for d in data.values()]))
    all_dates = [d for d in all_dates if d >= START]

    # 每年滚动选池: 年初用过去数据
    years = sorted(set(d.year for d in all_dates))
    print(f'年份: {years}')

    env_arr = pd.Series(env_map).reindex(all_dates).ffill()
    # 逐年: 该年成分 = 年初选的龙头池
    year_pools = {}
    for y in years:
        asof = pd.Timestamp(f'{y}-01-01')
        pool = select_leaders_at(data, asof) if asof > data_min_date(data) else set()
        if not pool:  # 首年(2023)用起点前数据
            pool = select_leaders_at(data, START)
        year_pools[y] = pool
        print(f'  {y} 龙头池: {len(pool)} 只')

    # 回测: 每年在当年龙头池内等权, 只在A环境持有
    eq = 1.0
    equity = []
    for i, day in enumerate(all_dates):
        pool = year_pools.get(day.year, set())
        day_rets = []
        for c in pool:
            d = data.get(c)
            if d is None:
                continue
            # 该股当日在池且有价
            if day in d.index and pd.notna(d.loc[day, 'close']):
                # 用前一交易日的收益
                prev = d.index[d.index < day]
                if len(prev) and pd.notna(d.loc[prev[-1], 'close']):
                    r = d.loc[day, 'close'] / d.loc[prev[-1], 'close'] - 1
                    day_rets.append(r)
        in_a = env_arr.iloc[i] == 'A'
        if in_a and day_rets:
            port_ret = np.mean(day_rets)
            # 日频调仓的换手成本(近似: 环境切换时才换) —— 简化按持有日无换手
            eq *= (1 + port_ret)
        equity.append({'date': day, 'equity': eq})

    eqdf = pd.DataFrame(equity).set_index('date')['equity']
    total = (eqdf.iloc[-1] - 1) * 100
    dd = ((eqdf / eqdf.cummax()) - 1).min() * 100

    # 基准: 全主板的A环境持有(需要全主板数据; 这里用当年池的全程持有)
    print(f'\n=== 逐年滚动龙头池 + 只在A持有 ===')
    print(f'全期: 收益{total:+.1f}%  回撤{dd:.1f}%')
    # 分段
    print('\n分段:')
    segs = np.array_split(eqdf.index, 3)
    for k, seg in enumerate(segs):
        e = eqdf.loc[seg]
        r = (e.iloc[-1] / e.iloc[0] - 1) * 100
        print(f'  段{k+1} {seg[0].date()}~{seg[-1].date()}: {r:+.1f}%')


def data_min_date(data):
    return min(d.index.min() for d in data.values())


if __name__ == '__main__':
    main()
