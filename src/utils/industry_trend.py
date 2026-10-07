# -*- coding: utf-8 -*-
"""
行业走势选主线 —— 用"龙头平均走势"取代"涨停热度"(用户指出的正确方法)
========================================================================
用户原话: "你为啥不看龙头的平均这个走势, 这样才好"

逻辑:
  1. 每个行业的**市值龙头**(龙头池)等权价格指数 = 该行业"龙头平均走势"
  2. 按该走势的**长期趋势**(近1年/近3年 + 相对全市场)排序 → 选强行业
  3. 选股: 强势行业内, 取**市值**龙头(不再用成交额)

与涨停热度的区别:
  - 涨停热度 = 游资短线信号(中文在线能排第一) → 已弃用
  - 龙头平均走势 = 规模/趋势信号(与中长线定位一致) → 采用

无前视: 用截至 T-1 的数据计算。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR


def build_leader_trend(price_data=None, pool_file='stock_pool_leaders_mc.csv'):
    """
    各行业"龙头等权价格指数"(= 龙头平均走势)。
    price_data: {code: Series(close, index=date)}; None则从缓存加载龙头池
    返回: DataFrame(index=date, columns=industry)
    """
    from src.data_loader import DataLoader
    loader = DataLoader()
    pool = pd.read_csv(os.path.join(DATA_DIR, pool_file), dtype={'code': str})
    pool['code'] = pool['code'].str.zfill(6)

    sers = {}
    for _, r in pool.iterrows():
        code, ind = r['code'], r['industry']
        if price_data is not None and code in price_data:
            s = price_data[code]
        else:
            df = loader.load_cache(code)
            if df is None or len(df) < 120:
                continue
            df = df.copy(); df['date'] = pd.to_datetime(df['date'])
            s = df.set_index('date')['close']
        sers.setdefault(ind, []).append(s.rename(code))

    out = {}
    for ind, lst in sers.items():
        if len(lst) < 2:
            continue
        mat = pd.concat(lst, axis=1).sort_index()
        norm = mat.ffill() / mat.ffill().bfill().iloc[0]
        out[ind] = norm.mean(axis=1)
    return pd.DataFrame(out).sort_index()


def rank_by_trend(trend, asof=None, lookback_long=250, lookback_mid=60):
    """
    按龙头平均走势给行业排名。
    返回 DataFrame: 行业 / 近60日 / 近250日 / 相对强度(vs全行业平均)
    """
    px = trend if asof is None else trend.loc[:pd.Timestamp(asof)]
    if len(px) < lookback_long + 5:
        return pd.DataFrame()
    mkt = px.mean(axis=1)   # 全行业等权 = 市场基准
    rows = []
    for ind in px.columns:
        s = px[ind].dropna()
        if len(s) < lookback_mid + 5:
            continue
        ret_mid = (s.iloc[-1] / s.iloc[-lookback_mid] - 1) * 100
        ret_long = (s.iloc[-1] / s.iloc[-lookback_long] - 1) * 100 if len(s) > lookback_long else None
        m_mid = (mkt.iloc[-1] / mkt.iloc[-lookback_mid] - 1) * 100
        rs = ret_mid - m_mid     # 相对强度
        rows.append({'行业': ind,
                     '近60日%': round(ret_mid, 1),
                     '近250日%': round(ret_long, 1) if ret_long is not None else None,
                     '相对强度pp': round(rs, 1)})
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df
    # 综合分 = 60日与250日的均值(都强才算强)
    df['综合'] = df[['近60日%', '近250日%']].mean(axis=1)
    return df.sort_values('综合', ascending=False).reset_index(drop=True)


def select_main_industries(trend, asof=None, top_n=5, min_long=0.0):
    """
    选主线行业: 龙头平均走势**近250日为正**且综合排名前列。
    (长期为负的行业即便短期反弹也不选 —— 用户: 长期走弱无反转不碰)
    """
    rk = rank_by_trend(trend, asof)
    if len(rk) == 0:
        return [], rk
    strong = rk[(rk['近250日%'].notna()) & (rk['近250日%'] >= min_long)]
    top = strong.head(top_n)
    return top['行业'].tolist(), rk


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    trend = build_leader_trend()
    inds, rk = select_main_industries(trend, top_n=10)
    print('=== 按"龙头平均走势"排名的行业 (前15) ===')
    print(rk.head(15).to_string(index=False))
    print(f'\n=== 选出的主线行业(近250日为正的前10) ===')
    for i in inds:
        print(f'  {i}')
    print('\n=== 末10(长期最弱, 应回避) ===')
    print(rk.tail(10).to_string(index=False))
