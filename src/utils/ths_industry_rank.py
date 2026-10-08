# -*- coding: utf-8 -*-
"""
行业走势选主线 v2 —— 用同花顺行业指数(市场口径)取代证监会84大类
====================================================================
用户指出: "零售业是龙头? 都没有半导体吗?"
根因: 证监会84大类又粗又杂(半导体/消费电子/元器件混在"C39计算机通信电子"),
      有些小桶平均值偶然排前 → 冒出"零售业"这种怪结果。

修正: 用同花顺90个行业指数(与同花顺App一致)的**长期走势**选强势行业。
数据: data/ths_industry_index/*.csv (由 src/utils/ths_industry.py --fetch 抓取)

用法: python -m src.utils.ths_industry_rank [--top 20]
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR

CACHE = os.path.join(DATA_DIR, 'ths_industry_index')


def load_index(name=None):
    """加载同花顺行业指数; name=None 返回全部(DataFrame)"""
    if not os.path.isdir(CACHE):
        return None
    data = {}
    files = [f'{name}.csv'] if name else [f for f in os.listdir(CACHE) if f.endswith('.csv')]
    for f in files:
        fp = os.path.join(CACHE, f)
        if not os.path.exists(fp):
            continue
        df = pd.read_csv(fp, parse_dates=['日期'])
        if len(df) > 250:
            data[f[:-4]] = df.set_index('日期')['收盘价']
    return pd.DataFrame(data).sort_index() if data else None


def rank_industries(asof=None, min_days=750):
    """
    按同花顺行业指数的长期走势排名。
    返回 DataFrame: 行业 / 近半年% / 近1年% / 近3年% / 综合
    """
    px = load_index()
    if px is None or len(px) == 0:
        return pd.DataFrame()
    if asof:
        px = px.loc[:pd.Timestamp(asof)]
    rows = []
    for name in px.columns:
        s = px[name].dropna()
        if len(s) < min_days:
            continue
        r6 = (s.iloc[-1] / s.iloc[-120] - 1) * 100 if len(s) > 120 else None
        r1 = (s.iloc[-1] / s.iloc[-250] - 1) * 100 if len(s) > 250 else None
        r3 = (s.iloc[-1] / s.iloc[-750] - 1) * 100 if len(s) > 750 else None
        rows.append({'行业': name,
                     '近半年%': round(r6, 1) if r6 is not None else None,
                     '近1年%': round(r1, 1) if r1 is not None else None,
                     '近3年%': round(r3, 1) if r3 is not None else None})
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df
    df['综合'] = df[['近半年%', '近1年%', '近3年%']].mean(axis=1)
    return df.sort_values('综合', ascending=False).reset_index(drop=True)


def select_main_industries(top_n=5, min_1y=0.0):
    """选主线行业: 近1年为正 且 综合排名前列(长期走弱的不选)"""
    rk = rank_industries()
    if len(rk) == 0:
        return [], rk
    strong = rk[(rk['近1年%'].notna()) & (rk['近1年%'] >= min_1y)]
    return strong.head(top_n)['行业'].tolist(), rk


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=20)
    args = ap.parse_args()
    rk = rank_industries()
    if len(rk) == 0:
        print('无同花顺行业指数缓存, 请先运行: python -m src.utils.ths_industry --fetch')
        sys.exit(1)
    print(f'=== 同花顺行业 按长期走势排名 (前{args.top}) ===')
    print(rk.head(args.top).to_string(index=False))
    print(f'\n=== 末10(长期最弱, 应回避) ===')
    print(rk.tail(10).to_string(index=False))
