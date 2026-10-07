# -*- coding: utf-8 -*-
"""
行业长期健康度 —— 中长线视角的行业过滤
========================================
用户原则: 做中长线, 若某行业**长期走弱且无反转迹象**, 即使今天热点也不碰。
  (例: 白酒今天涨得好, 但长期趋势向下且未反转 → 不在考虑范围)

与"情绪热度"(短线谁在涨停)互补: 情绪热度判"当下主线", 长期健康度判
"这个行业值不值得中长线关注"。

三维度(全部无前视, 用截至 T-1 的数据):
  1. 长期趋势: 行业内龙头池等权价的 250日斜率(年线方向)
  2. 中期趋势: 60日相对强弱(vs 全市场)
  3. 反转迹象: 近20日是否转正 / 是否站上长期均线

用法: python -m src.utils.industry_health [--asof YYYY-MM-DD]
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.data_loader import DataLoader

LONG_WIN = 250    # 长期(约1年)
MID_WIN = 60      # 中期


def build_industry_index(pool_file='stock_pool_leaders.csv', start='2014-01-01'):
    """各行业的等权价格指数(用龙头池成分, 缺失则用全池)"""
    loader = DataLoader()
    p = os.path.join(DATA_DIR, pool_file)
    if not os.path.exists(p):
        p = os.path.join(DATA_DIR, 'stock_pool.csv')
    pool = pd.read_csv(p, dtype={'code': str})
    pool['code'] = pool['code'].str.zfill(6)
    ind_map = dict(zip(pool['code'], pool.get('industry', pd.Series(dtype=str))))
    # 若池里没行业, join 行业分类
    if not ind_map or all(pd.isna(v) for v in ind_map.values()):
        ind = loader.get_industry()[['code_std', 'industry']].rename(columns={'code_std': 'code'})
        ind['code'] = ind['code'].astype(str).str.zfill(6)
        ind_map = dict(zip(ind['code'], ind['industry']))

    series = {}
    for c in pool['code']:
        df = loader.load_cache(c)
        if df is None or len(df) < 100 or c not in ind_map:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'] >= pd.Timestamp(start)]
        if len(df) < 100:
            continue
        s = df.set_index('date')['close']
        series.setdefault(ind_map[c], []).append(s.rename(c))
    # 每行业等权归一化指数
    out = {}
    for ind, lst in series.items():
        if len(lst) < 2:
            continue
        mat = pd.concat(lst, axis=1).sort_index()
        norm = mat / mat.ffill().bfill().iloc[0]
        out[ind] = norm.mean(axis=1)   # 等权平均(等权归一化后)
    return pd.DataFrame(out).sort_index(), ind_map


def health_score(ind_px, asof=None):
    """
    行业长期健康度: 返回 {industry: {lt_slope, mid_rs, reversal, verdict}}
    verdict ∈ {健康, 中性, 走弱无反转(剔除), 反转中}
    """
    df = ind_px if asof is None else ind_px.loc[:pd.Timestamp(asof)]
    if len(df) < LONG_WIN + 5:
        return {}
    last = df.iloc[-1]
    res = {}
    # 全市场基准(所有行业等权)
    mkt = df.mean(axis=1)
    for ind in df.columns:
        s = df[ind].dropna()
        if len(s) < MID_WIN + 5:
            continue
        # 1. 长期趋势: 250日收益(年线方向)
        lt = s.iloc[-1] / s.iloc[-LONG_WIN] - 1 if len(s) > LONG_WIN else np.nan
        # 2. 中期相对强弱: 60日行业收益 - 全市场60日收益
        m60 = mkt.dropna()
        ind60 = s.iloc[-1] / s.iloc[-MID_WIN] - 1
        mkt60 = m60.iloc[-1] / m60.iloc[-MID_WIN] - 1 if len(m60) > MID_WIN else 0
        rs = ind60 - mkt60
        # 3. 反转迹象(真正的转势): 站上250日均线 且 近20日向上
        #    —— 一个月的小反弹不算反转(用户原则: 长期走弱+无真反转=不碰)
        ma_long = s.rolling(LONG_WIN).mean().iloc[-1]
        r20 = s.iloc[-1] / s.iloc[-21] - 1 if len(s) > 21 else 0
        above_ma = s.iloc[-1] > ma_long if pd.notna(ma_long) else False
        real_reversal = bool(above_ma and r20 > 0)

        # 综合判定(中长线视角 —— 用户原则: 长期走弱且无真反转 → 剔除)
        if pd.notna(lt) and lt < -0.15 and not real_reversal:
            # 长期跌>15% 且 未站上年线/未转正 → 长期走弱无反转, 剔除
            verdict = '走弱无反转(剔除)'
        elif pd.notna(lt) and lt < -0.15 and real_reversal:
            verdict = '反转中'             # 长期弱但已站上年线且转正
        elif pd.notna(lt) and lt > 0.10 and rs > -0.05:
            verdict = '健康'
        else:
            verdict = '中性'
        res[ind] = {'lt_1y': round(lt * 100, 1) if pd.notna(lt) else None,
                    'mid_rs': round(rs * 100, 1), 'r20': round(r20 * 100, 1),
                    'above_ma250': bool(above_ma), 'verdict': verdict}
    return res


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--asof', default=None)
    args = ap.parse_args()

    px, _ = build_industry_index()
    hs = health_score(px, args.asof)
    if not hs:
        print('[!] 数据不足(需先拉长行业历史)'); return
    df = pd.DataFrame(hs).T.sort_values('lt_1y', ascending=False)
    print(f'=== 行业长期健康度(中长线视角) {args.asof or "最新"} ===')
    print('判定: 健康=长期向上且不跑输; 走弱无反转=剔除; 反转中=长期弱但转好')
    print(df.to_string())
    weak = [k for k, v in hs.items() if v['verdict'] == '走弱无反转(剔除)']
    print(f'\n剔除(长期走弱无反转): {len(weak)} 个行业')
    for w in weak:
        print(f'  - {w} (1年{hs[w]["lt_1y"]}%, 相对{hs[w]["mid_rs"]}%, 20日{hs[w]["r20"]}%)')


if __name__ == '__main__':
    main()
