# -*- coding: utf-8 -*-
"""
选行业 v3 —— "有前景" + "不接盘"(用户三点要求)
======================================================
用户要求(重要):
  1. 只买行业走势排名靠前 **且有前景** 的行业
  2. A股会"A杀"(急涨后急杀), 不能高位接盘
  3. "有前景"和"位置不高"是两个独立维度, 都要满足

判据(两个独立门槛):
  A. 有前景(长):  近1年>0 且 近3年>0   —— 行业真的在成长, 不是偶然反弹
  B. 不接盘(位置): 距250日高点回撤 ∈ [-35%, -3%] —— 既不在最高位接盘, 也不接下跌中的刀
     且 近20日涨幅 < 15%(不过热, 避开"A杀"前夕)
  综合分 = 有前景程度 与 位置(偏中低位)的加权; 只取同时满足A和B的行业

用法: python -m src.utils.industry_trend_v3
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR

CACHE = os.path.join(DATA_DIR, 'ths_industry_index')


def load_index():
    if not os.path.isdir(CACHE):
        return None
    data = {}
    for f in os.listdir(CACHE):
        if not f.endswith('.csv'):
            continue
        df = pd.read_csv(os.path.join(CACHE, f), parse_dates=['日期'])
        if len(df) > 750:
            data[f[:-4]] = df.set_index('日期')[['开盘价', '最高价', '最低价', '收盘价']].rename(
                columns={'开盘价': 'open', '最高价': 'high', '最低价': 'low', '收盘价': 'close'})
    return data


def score_industry(df, asof=None):
    """
    单行业打分: 返回 {近1年, 近3年, 距250日高回撤, 近20日, 有前景, 不接盘} 或 None
    """
    if asof:
        df = df[df.index <= pd.Timestamp(asof)]
    if len(df) < 260:
        return None
    c = df['close']
    hi = df['high']
    last = c.iloc[-1]
    r1 = (last / c.iloc[-250] - 1) * 100 if len(c) > 250 else None
    r3 = (last / c.iloc[-750] - 1) * 100 if len(c) > 750 else None
    r20 = (last / c.iloc[-21] - 1) * 100 if len(c) > 21 else None
    high250 = hi.iloc[-250:].max()
    dd = (last / high250 - 1) * 100            # 距250日高点的回撤(负=低于高点)
    # A. 有前景: 长期趋势向上
    future = (r1 is not None and r1 > 0) and (r3 is not None and r3 > 0)
    # B. 不接盘: 位置不高不低 + 不过热
    not_chase = (-35 <= dd <= -3) and (r20 is not None and r20 < 15)
    return {'近1年%': round(r1, 1) if r1 is not None else None,
            '近3年%': round(r3, 1) if r3 is not None else None,
            '距高点%': round(dd, 1),
            '近20日%': round(r20, 1) if r20 is not None else None,
            '有前景': future, '不接盘': not_chase}


def select(top_n=5, asof=None):
    """选出同时满足"有前景"和"不接盘"的行业, 按位置(偏中低位)排序"""
    idx = load_index()
    if idx is None:
        return pd.DataFrame()
    rows = []
    for name, df in idx.items():
        s = score_industry(df, asof)
        if s is None:
            continue
        rows.append({'行业': name, **s})
    df = pd.DataFrame(rows)
    df['入选'] = df['有前景'] & df['不接盘']
    # 排序: 入选优先; 入选内按 近1年 温和为正 + 距高点适中 排序
    df = df.sort_values(['入选', '近1年%'], ascending=[False, False]).reset_index(drop=True)
    return df


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    df = select()
    if len(df) == 0:
        print('无同花顺行业数据'); return
    picked = df[df['入选']]
    print(f'=== 同时满足"有前景"+"不接盘"的行业 ({len(picked)}/{len(df)}) ===')
    print(picked[['行业', '近1年%', '近3年%', '距高点%', '近20日%']].head(20).to_string(index=False))
    print(f'\n=== 有前景但高位(会接盘, 剔除) ===')
    high = df[(df['有前景']) & (~df['不接盘'])]
    print(high[['行业', '近1年%', '近3年%', '距高点%', '近20日%']].head(15).to_string(index=False))
    print(f'\n=== 没前景(剔除) ===')
    nf = df[~df['有前景']]
    print(nf[['行业', '近1年%', '近3年%', '距高点%']].head(8).to_string(index=False))


if __name__ == '__main__':
    main()
