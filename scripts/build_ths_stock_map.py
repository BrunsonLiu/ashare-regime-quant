# -*- coding: utf-8 -*-
"""
股票→同花顺行业 映射 —— 用收益相关性匹配(离线可行)
======================================================
问题: 同花顺行业指数有(90个, 市场口径), 但没有"股票属于哪个同花顺行业"的
      官方映射接口(东财/申万/同花顺成分股接口在此沙箱均不可达)。
方案: 用**收益率相关性**把每只股票归到走势最相关的同花顺行业。
      对"按行业走势选股"这个用途足够(我们要的就是走势相近的股票)。

输出: data/ths_stock_industry.csv  (code, name, industry, corr)
用法: python scripts/build_ths_stock_map.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8')

from src.data_loader import DataLoader
from src.utils.ths_industry_rank import load_index


def main():
    loader = DataLoader()
    idx = load_index()          # 同花顺行业指数(90个)
    if idx is None:
        print('无同花顺行业指数, 先运行 python -m src.utils.ths_industry --fetch'); return
    # 用近500日收益做相关性
    idx_ret = idx.tail(500).pct_change().dropna(how='all')
    ind_names = list(idx_ret.columns)

    pool = pd.read_csv(os.path.join(ROOT, 'data', 'stock_pool.csv'), dtype={'code': str})
    codes = pool['code'].str.zfill(6).tolist()
    ind_meta = loader.get_industry()[['code_std', 'code_name']]
    ind_meta['code'] = ind_meta['code_std'].astype(str).str.zfill(6)
    name_map = dict(zip(ind_meta['code'], ind_meta['code_name']))

    rows = []
    n = 0
    for c in codes:
        df = loader.load_cache(c)
        if df is None or len(df) < 400:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        s = df.set_index('date')['close'].pct_change().tail(500)
        s = s.reindex(idx_ret.index)
        if s.notna().sum() < 200:
            continue
        # 与各行业指数收益的相关性
        best_ind, best_corr = None, -2
        for name in ind_names:
            r = s.corr(idx_ret[name])
            if pd.notna(r) and r > best_corr:
                best_corr, best_ind = r, name
        if best_ind:
            rows.append({'code': c, 'name': name_map.get(c, ''),
                         'industry': best_ind, 'corr': round(float(best_corr), 3)})
        n += 1
        if n % 500 == 0:
            print(f'  {n} 只...', flush=True)

    out = pd.DataFrame(rows)
    fp = os.path.join(ROOT, 'data', 'ths_stock_industry.csv')
    out.to_csv(fp, index=False, encoding='utf-8-sig')
    print(f'\n[OK] {len(out)} 只 → {fp}')
    print('\n各同花顺行业股票数(前15):')
    print(out['industry'].value_counts().head(15).to_string())


if __name__ == '__main__':
    main()
