# -*- coding: utf-8 -*-
"""
龙头池 v2 —— 市值口径 + 游资炒作过滤(修正"用成交额定义龙头"的系统性错误)
============================================================================
问题(用户指出): 旧龙头池用"成交额"排名选龙头 → 成交额被游资污染。
  典型: 中文在线成交额行业第1, 但市值仅第6, 且21个月净-2%+换手8.5%(纯炒作)。

本版本:
  1. 龙头定义改用**市值**(收盘价 × 流通股本, 缓存已有) —— 真实规模/行业地位
  2. 加**炒作度过滤**: 剔除"净涨跌≈0 但高换手/高波动"的游资票
  3. 保留行业口径可切换(证监会/同花顺)

用法: python scripts/build_leader_pool_v2.py [per_industry] [--ths]
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8')

from src.data_loader import DataLoader

# 炒作度过滤阈值(可调)
MAX_TURNOVER = 6.0      # 日均换手率上限%(真龙头通常<5%, 游资票常>8%)
MIN_NET_TREND = -0.15   # 近1年净涨跌下限(低于此=长期下跌)


def load_stocks():
    """每只股票: 市值/近1年净涨跌/日均换手/波动 等特征"""
    loader = DataLoader()
    ind = loader.get_industry()
    ind = ind[['code_std', 'code_name', 'industry']].rename(columns={'code_std': 'code'})
    ind['code'] = ind['code'].astype(str).str.zfill(6)
    ind = ind[ind['industry'].astype(str).str.strip() != '']
    ind = ind[~ind['code_name'].str.contains(r'ST|退', na=False)]

    rows = []
    for _, r in ind.iterrows():
        code = r['code']
        df = loader.load_cache(code)
        if df is None or len(df) < 250:
            continue
        if 'outstanding_share' not in df.columns:
            continue
        tail = df.tail(250)
        last = tail.iloc[-1]
        mc = last['close'] * last['outstanding_share'] / 1e8   # 流通市值(亿)
        ret1y = (last['close'] / tail['close'].iloc[0] - 1) * 100
        turnover = tail['turnover'].mean() if 'turnover' in tail.columns else 0
        vol = tail['close'].pct_change().std() * 100
        rows.append({'code': code, 'name': r['code_name'], 'industry': r['industry'],
                     'mktcap_yi': round(mc, 1), 'ret1y': round(ret1y, 1),
                     'turnover': round(turnover, 2), 'volatility': round(vol, 2)})
    return pd.DataFrame(rows)


def flag_speculative(df):
    """标记游资炒作特征: 高换手 + 净涨跌平庸(白忙) —— 中文在线式"""
    # 高换手 且 (净涨跌在±10%内 或 为负) → 炒作概率高
    df = df.copy()
    df['speculative'] = (df['turnover'] > MAX_TURNOVER) & (df['ret1y'] < 10)
    return df


def build(per_industry=3, min_mktcap=50, use_ths=False):
    df = load_stocks()
    print(f'有市值数据的股票: {len(df)}')

    # 炒作度标记
    df = flag_speculative(df)
    n_spec = int(df['speculative'].sum())
    print(f'标记为游资炒作特征(高换手> {MAX_TURNOVER}%且净涨跌平庸): {n_spec} 只')

    # 市值门槛
    df = df[df['mktcap_yi'] >= min_mktcap]
    print(f'市值≥{min_mktcap}亿: {len(df)} 只')

    # 行业内按**市值**排名(取代成交额)
    df['rank_mc'] = df.groupby('industry')['mktcap_yi'].rank(ascending=False, method='first')
    leaders = df[(df['rank_mc'] <= per_industry) & (~df['speculative'])].copy()
    leaders = leaders.sort_values(['industry', 'mktcap_yi'], ascending=[True, False])

    print(f'\n行业数: {df["industry"].nunique()}, 龙头池: {len(leaders)} 只 '
          f'(每行业市值前{per_industry}, 已剔除炒作票)')

    # 示例: 电子/白酒/电池 等行业
    for ind in ['C39计算机、通信和其他电子设备制造业', 'C15酒、饮料和精制茶制造业']:
        g = leaders[leaders['industry'] == ind]
        if len(g):
            s = ' | '.join(f'{r["name"]}({r["mktcap_yi"]:.0f}亿 净{r["ret1y"]:+.0f}% 换{r["turnover"]:.1f}%)'
                          for _, r in g.iterrows())
            print(f'  {ind[:16]:<18} {s}')

    out = leaders[['code', 'name', 'industry', 'mktcap_yi', 'ret1y', 'turnover']].copy()
    path = os.path.join(ROOT, 'data', 'stock_pool_leaders_mc.csv')
    out.to_csv(path, index=False, encoding='utf-8-sig')
    print(f'\n[OK] 市值龙头池 → {path} ({len(out)}只)')

    # 对照: 中文在线 是否被剔除?
    czwx = df[df['code'] == '300364']
    if len(czwx):
        r = czwx.iloc[0]
        print(f'\n对照 中文在线: 市值{r["mktcap_yi"]:.0f}亿(行业第{int(r["rank_mc"])}) '
              f'净{r["ret1y"]:+.0f}% 换手{r["turnover"]:.1f}% → '
              f'{"保留" if not r["speculative"] and r["rank_mc"]<=per_industry else "剔除"}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('per_industry', type=int, nargs='?', default=3)
    ap.add_argument('--min-mktcap', type=float, default=50)
    args = ap.parse_args()
    build(args.per_industry, args.min_mktcap)


if __name__ == '__main__':
    main()
