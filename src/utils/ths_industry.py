# -*- coding: utf-8 -*-
"""
同花顺行业数据 —— 用市场实际使用的行业口径(取代证监会84大类)
================================================================
用户指出: 证监会分类与同花顺不一致(宁德时代被塞进"电气机械和器材"),
选出来的"行业"和交易员认知对不上。

同花顺行业指数(ak.stock_board_industry_index_ths):
  - 90个行业板块, 与同花顺App一致(半导体/白酒/电池/银行...)
  - 提供行业指数历史OHLC → 正是"行业平均走势"
  - 用于: 按长期走势选行业(取代涨停热度)

用法:
  python -m src.utils.ths_industry --list                 # 列出全部行业
  python -m src.utils.ths_industry --rank                 # 按长期走势排名
"""
import argparse
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR

CACHE = os.path.join(DATA_DIR, 'ths_industry_index')


def list_industries():
    """同花顺行业板块列表 [{name, code}]"""
    import akshare as ak
    return ak.stock_board_industry_name_ths()


def fetch_industry_index(name, start='20140101', end=None, use_cache=True):
    """单行业指数历史(带本地缓存)"""
    end = end or pd.Timestamp.now().strftime('%Y%m%d')
    os.makedirs(CACHE, exist_ok=True)
    fp = os.path.join(CACHE, f'{name}.csv')
    if use_cache and os.path.exists(fp):
        df = pd.read_csv(fp, parse_dates=['日期'])
        # 缓存够新(3天内)则直接用
        if len(df) and (pd.Timestamp.now() - df['日期'].max()).days <= 3:
            return df
    import akshare as ak
    df = ak.stock_board_industry_index_ths(symbol=name, start_date=start, end_date=end)
    if df is None or len(df) == 0:
        return None
    df['日期'] = pd.to_datetime(df['日期'])
    df.to_csv(fp, index=False, encoding='utf-8-sig')
    return df


def build_all(codes, sleep=0.3):
    """批量抓取全部行业指数(带缓存)"""
    out = {}
    for name in codes:
        try:
            df = fetch_industry_index(name)
            if df is not None and len(df) > 250:
                out[name] = df.set_index('日期')['收盘价']
        except Exception as e:
            print(f'  [skip] {name}: {str(e)[:50]}')
        time.sleep(sleep)
    return pd.DataFrame(out).sort_index()


def rank_industries(px):
    """按长期走势给行业排名(近1年/近3年 + 相对强度)"""
    rows = []
    for name in px.columns:
        s = px[name].dropna()
        if len(s) < 260:
            continue
        r1 = (s.iloc[-1] / s.iloc[-250] - 1) * 100 if len(s) > 250 else None
        r3 = (s.iloc[-1] / s.iloc[-750] - 1) * 100 if len(s) > 750 else None
        r6 = (s.iloc[-1] / s.iloc[-120] - 1) * 100 if len(s) > 120 else None
        rows.append({'行业': name, '近半年%': round(r6, 1) if r6 else None,
                     '近1年%': round(r1, 1) if r1 else None,
                     '近3年%': round(r3, 1) if r3 else None})
    df = pd.DataFrame(rows)
    # 综合排序: 优先近1年与近3年都强
    df['综合'] = df[['近1年%', '近3年%']].mean(axis=1)
    return df.sort_values('综合', ascending=False)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true', help='列出全部行业')
    ap.add_argument('--rank', action='store_true', help='按长期走势排名(需先抓取)')
    ap.add_argument('--fetch', action='store_true', help='抓取全部行业指数')
    ap.add_argument('--top', type=int, default=20)
    args = ap.parse_args()

    if args.list:
        df = list_industries()
        print(f'同花顺行业: {len(df)} 个')
        print(df.to_string(index=False))
        return

    if args.fetch:
        names = list_industries()['name'].tolist()
        print(f'抓取 {len(names)} 个行业指数...')
        px = build_all(names)
        px.to_csv(os.path.join(DATA_DIR, 'ths_industry_px.csv'), encoding='utf-8-sig')
        print(f'[OK] {px.shape[1]} 个行业 × {len(px)} 天 → data/ths_industry_px.csv')
        return

    if args.rank:
        fp = os.path.join(DATA_DIR, 'ths_industry_px.csv')
        if not os.path.exists(fp):
            print('请先运行 --fetch'); return
        px = pd.read_csv(fp, index_col=0, parse_dates=True)
        df = rank_industries(px)
        print(f'=== 同花顺行业 按长期走势排名 (前{args.top}) ===')
        print(df.head(args.top).to_string(index=False))
        print(f'\n=== 末{args.top} (长期最弱) ===')
        print(df.tail(args.top).to_string(index=False))
        return

    print(__doc__)


if __name__ == '__main__':
    main()
