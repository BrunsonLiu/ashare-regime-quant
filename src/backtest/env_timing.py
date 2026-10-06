# -*- coding: utf-8 -*-
"""
环境择时检验 —— 守则"环境决定持有"的纯净验证
================================================
与回测引擎的区别: 这里检验的是**组合级择时**(在哪个环境持有),
不含个股换手 —— 因为龙头池的教训是"换手毁灭价值", 要把择时信号
从换手噪声里剥离出来单独看。

方法(零换手成本, 组合级):
- 龙头池等权日收益 → 按环境 mask 持有(非持有日收益=0=空仓)
- 报告全程持有 vs 各环境子集 的收益/回撤, 并分段检验稳健性

用法: python -m src.backtest.env_timing
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from src.utils.market_env import MarketEnvironment, load_sentiment
from src.data_loader import DataLoader
from config import DATA_DIR

START = '2023-09-08'   # 指数/情绪重叠起点


def build_portfolio_returns(leaders_only=True):
    """龙头池等权日收益 + 环境序列(对齐)"""
    loader = DataLoader()
    idx = loader.get_index_data('000001', days=1300)
    idx['date'] = pd.to_datetime(idx['date'])
    env_map, envdf = MarketEnvironment().classify_series(idx, load_sentiment())

    pool_file = 'stock_pool_leaders.csv' if leaders_only else 'stock_pool.csv'
    codes = pd.read_csv(os.path.join(DATA_DIR, pool_file),
                        dtype={'code': str})['code'].str.zfill(6).tolist()
    port = {}
    for c in codes:
        df = loader.load_cache(c)
        if df is None or len(df) < 100:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        port[c] = df.set_index('date')['close']

    prices = pd.DataFrame(port).sort_index()
    prices = prices.loc[prices.index >= pd.Timestamp(START)]
    rets = prices.pct_change(fill_method=None).mean(axis=1)
    envs = pd.Series(env_map).reindex(rets.index).ffill()
    return rets, envs, len(port)


def eval_mask(rets, mask):
    r = rets.where(mask, 0.0).fillna(0.0)
    eq = (1 + r).cumprod()
    total = float(eq.iloc[-1] - 1)
    peak = eq.cummax()
    dd = float(((eq - peak) / peak).min())
    return {'ret_pct': round(total * 100, 1), 'max_dd_pct': round(dd * 100, 1),
            'days_in': int(mask.sum())}


def run_all(save=True):
    rets, envs, n = build_portfolio_returns()
    print(f'龙头池 {n} 只, {len(rets)} 个交易日 ({rets.index[0].date()} ~ {rets.index[-1].date()})')
    print('环境分布:', {k: int((envs == k).sum()) for k in ('A', 'B', 'C', 'D')})

    variants = {
        '全程持有(买入持有)': pd.Series(True, index=rets.index),
        '只在A主线': envs == 'A',
        '只在B散乱': envs == 'B',
        '避开B散乱': envs != 'B',
        '只在非D': envs != 'D',
        '只在A+C': envs.isin(['A', 'C']),
        '只在D熊市': envs == 'D',
    }
    print('\n=== 组合级环境择时(零换手, 龙头池等权) ===')
    rows = []
    for label, mask in variants.items():
        st = eval_mask(rets, mask)
        print(f'  {label:20} 收益{st["ret_pct"]:+7.1f}%  回撤{st["max_dd_pct"]:6.1f}%  在场{st["days_in"]:3}天')
        rows.append({'variant': label, **st})

    # 分段稳健性: 3 段
    print('\n=== 3段稳健性(只在A主线 vs 全程持有) ===')
    seg_bounds = np.array_split(rets.index, 3)
    for i, seg in enumerate(seg_bounds):
        rs = rets.loc[seg]; es = envs.loc[seg]
        all_st = eval_mask(rs, pd.Series(True, index=rs.index))
        a_st = eval_mask(rs, es == 'A')
        print(f'  段{i+1} {seg[0].date()}~{seg[-1].date()}: '
              f'持有{all_st["ret_pct"]:+6.1f}%  只A{a_st["ret_pct"]:+6.1f}%')

    df = pd.DataFrame(rows)
    if save:
        out_dir = os.path.join(DATA_DIR, 'experiments')
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, f'env_timing_{pd.Timestamp.now():%Y%m%d_%H%M}.csv')
        df.to_csv(p, index=False, encoding='utf-8-sig')
        print(f'\n[OK] → {p}')
    return df


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run_all()
