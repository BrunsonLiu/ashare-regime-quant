# -*- coding: utf-8 -*-
"""
构建"行业龙头池" —— 只玩行业龙头, 杂毛不玩
=============================================
守则2.3定义龙头: 成交额全市场前列 / 板块内率先涨停 / 有连板基因。
离线可复现的口径: **行业内成交额(流动性/规模代理)领先的前 N 家**。

原则(用户原话): 如果这个企业在行业里啥也不是, 我们不玩。

用法: python scripts/build_leader_pool.py [top_n_per_industry] [min_avg_amount_yi]
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8')

from src.data_loader import DataLoader

TOP_N = 3            # 每个行业取前N家(守则"成交额前3")
MIN_AMOUNT_YI = 0.5  # 日均成交额门槛(亿)——太小的直接不算龙头
LOOKBACK = 250       # 用最近约1年成交额算规模


def main():
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else TOP_N
    min_amt = (float(sys.argv[2]) if len(sys.argv) > 2 else MIN_AMOUNT_YI) * 1e8

    loader = DataLoader()
    # 1. 行业分类(证监会84类), 只保留有行业、非ST、非退市的A股
    ind = loader.get_industry()
    ind = ind[['code_std', 'code_name', 'industry']].rename(columns={'code_std': 'code'})
    ind = ind[ind['industry'].astype(str).str.strip() != '']
    ind = ind[~ind['code_name'].str.contains(r'ST|退', na=False)]
    ind = ind[ind['code'].astype(str).str.match(r'^(60|00|30|68)')]

    # 2. 每只股票的近期日均成交额(规模代理, 取自本地日线缓存)
    rows = []
    for _, r in ind.iterrows():
        code = str(r['code']).zfill(6)
        df = loader.load_cache(code)
        if df is None or len(df) < 60:
            continue
        tail = df.tail(LOOKBACK)
        avg_amt = float(tail['amount'].mean())
        rows.append({'code': code, 'name': r['code_name'], 'industry': r['industry'],
                     'avg_amount': avg_amt, 'days': len(tail)})
    df = pd.DataFrame(rows)
    print(f'有行情+行业分类的股票: {len(df)}')

    # 3. 行业内按成交额排序, 取前N, 且过成交额门槛
    df = df[df['avg_amount'] >= min_amt]
    df['rank_in_ind'] = df.groupby('industry')['avg_amount'].rank(ascending=False, method='first')
    leaders = df[df['rank_in_ind'] <= top_n].copy()
    leaders = leaders.sort_values(['industry', 'avg_amount'], ascending=[True, False])

    # 4. 报告
    print(f'\n行业数: {df["industry"].nunique()}, 龙头池: {len(leaders)} 只 '
          f'(每行业前{top_n}, 日均成交额≥{min_amt/1e8:.1f}亿)')
    print('\n各行业龙头(前15个行业示例):')
    for industry, g in list(leaders.groupby('industry'))[:15]:
        names = ' | '.join(f'{r["name"]}({r["avg_amount"]/1e8:.1f}亿)'
                          for _, r in g.head(top_n).iterrows())
        print(f'  {industry[:24]:<26} {names}')

    # 5. 落盘
    out = leaders[['code', 'name', 'industry', 'avg_amount', 'rank_in_ind']].copy()
    out['avg_amount_yi'] = (out['avg_amount'] / 1e8).round(3)
    out = out.drop(columns=['avg_amount'])
    path = os.path.join(ROOT, 'data', 'stock_pool_leaders.csv')
    out.to_csv(path, index=False, encoding='utf-8-sig')
    print(f'\n[OK] 龙头池 → {path} ({len(out)}只)')
    print(f'     下一步: 用 --pool leaders 让回测/实验只在这批股票里选股')


if __name__ == '__main__':
    main()
