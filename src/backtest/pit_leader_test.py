# -*- coding: utf-8 -*-
"""
时点(PIT)龙头池 —— 消除选池的前视偏差
========================================
此前龙头池用"全期(2023-2026)成交额"选龙头, 而回测期含在其中 →
选池用了未来信息(前视偏差), 会高估龙头效应。

本脚本: 只用**回测起点之前**的数据选龙头(时点正确), 再往后回测,
对比"PIT龙头池 vs 全池", 看龙头效应是否在无前视下依然成立。

用法: python -m src.backtest.pit_leader_test --split 2023-09-08
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.data_loader import DataLoader


def build_pit_leaders(split_date, top_n_per_ind=3, min_amt_yi=0.3):
    """只用 split_date 之前的行情选龙头(时点正确, 无前视)"""
    loader = DataLoader()
    ind = loader.get_industry()
    ind = ind[['code_std', 'code_name', 'industry']].rename(columns={'code_std': 'code'})
    ind = ind[ind['industry'].astype(str).str.strip() != '']
    ind = ind[~ind['code_name'].str.contains(r'ST|退', na=False)]
    ind = ind[ind['code'].astype(str).str.match(r'^(60|00|30|68)')]

    split = pd.Timestamp(split_date)
    rows = []
    for _, r in ind.iterrows():
        code = str(r['code']).zfill(6)
        df = loader.load_cache(code)
        if df is None or len(df) < 40:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        past = df[df['date'] < split]          # 只用回测起点之前
        if len(past) < 40:
            continue
        rows.append({'code': code, 'name': r['code_name'], 'industry': r['industry'],
                     'past_amt': float(past['amount'].mean())})
    df = pd.DataFrame(rows)
    df = df[df['past_amt'] >= min_amt_yi * 1e8]
    df['rank'] = df.groupby('industry')['past_amt'].rank(ascending=False, method='first')
    leaders = df[df['rank'] <= top_n_per_ind].copy()
    return leaders


def bh_returns(codes, start, end):
    loader = DataLoader()
    rets = []
    for c in codes:
        df = loader.load_cache(c)
        if df is None:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        sub = df[(df['date'] >= pd.Timestamp(start)) & (df['date'] <= pd.Timestamp(end))]
        if len(sub) < 100:
            continue
        rets.append(sub['close'].iloc[-1] / sub['close'].iloc[0] - 1)
    return (np.mean(rets) * 100 if rets else np.nan,
            np.median(rets) * 100 if rets else np.nan, len(rets))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--split', default='2023-09-08', help='回测起点(也是选池截止)')
    ap.add_argument('--end', default='2026-09-30')
    args = ap.parse_args()

    pit = build_pit_leaders(args.split)
    print(f'PIT龙头池(仅用{args.split}前数据选): {len(pit)} 只, '
          f'{pit["industry"].nunique()} 行业')

    full = pd.read_csv(os.path.join(DATA_DIR, 'stock_pool.csv'), dtype={'code': str})
    full_codes = full['code'].str.zfill(6).tolist()

    # 注意: 公司可能在split前未上市/无数据 → PIT池天然只含当时已存在的
    pm, pmed, pn = bh_returns(pit['code'].tolist(), args.split, args.end)
    fm, fmed, fn = bh_returns(full_codes, args.split, args.end)

    print(f'\n=== {args.split} ~ {args.end} 买入持有(无前视选池) ===')
    print(f'PIT龙头池({pn}只): 均值{pm:+.1f}%  中位{pmed:+.1f}%')
    print(f'全池({fn}只):      均值{fm:+.1f}%  中位{fmed:+.1f}%')
    print(f'龙头优势:          均值{pm-fm:+.1f}pp  中位{pmed-fmed:+.1f}pp')

    # 对照: 用全期数据选池(含前视)的"旧"龙头池
    old = pd.read_csv(os.path.join(DATA_DIR, 'stock_pool_leaders.csv'), dtype={'code': str})
    om, omed, on = bh_returns(old['code'].str.zfill(6).tolist(), args.split, args.end)
    print(f'\n对照-旧龙头池(全期成交额选, 含前视, {on}只): 均值{om:+.1f}% 中位{omed:+.1f}%')
    print(f'→ 前视使选池收益虚增约 {om-pm:+.1f}pp(均值) / {omed-pmed:+.1f}pp(中位)')

    out = pit[['code', 'name', 'industry', 'past_amt']].copy()
    out['past_amt_yi'] = (out['past_amt'] / 1e8).round(3)
    path = os.path.join(DATA_DIR, 'stock_pool_leaders_pit.csv')
    out.drop(columns=['past_amt']).to_csv(path, index=False, encoding='utf-8-sig')
    print(f'\n[OK] PIT龙头池 → {path}')


if __name__ == '__main__':
    main()
