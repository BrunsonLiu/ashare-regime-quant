# -*- coding: utf-8 -*-
"""
市场结构画像 —— 用日线量价读"力量/位置/博弈/节奏"(不是判前景)
================================================================
用户要求: 把"市场的力量/趋势/博弈/节奏"融合进模型。
分清边界(重要):
  量价能读 → 力量/位置/博弈/节奏(结构)
  量价读不出 → 前景(产业/基本面属性, 量价只是影子)

本模块读结构, 用于**否决**: 拦住"高位接盘"和"接下跌刀"。
判据全部可解释、可复现, 无前视(只用截至某日的数据)。

用法: python -m src.utils.market_structure --code 601118
      python -m src.utils.market_structure --compare 601118,300308,300364
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.data_loader import DataLoader


def analyze(df, asof=None, lookback=250, industry_df=None):
    """
    单只股票的结构画像(截至 asof)。
    返回 {力量, 位置, 博弈, 节奏, 否决, 理由}
    """
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    if asof:
        df = df[df['date'] <= pd.Timestamp(asof)]
    df = df.tail(lookback).reset_index(drop=True)
    if len(df) < 120:
        return None

    close = df['close']; high = df['high']; low = df['low']; vol = df['volume']
    last = close.iloc[-1]
    ret = close.pct_change()

    # ===== 1. 力量: 上涨日的量 vs 下跌日的量 =====
    up = vol[ret > 0].mean() if (ret > 0).any() else 0
    dn = vol[ret < 0].mean() if (ret < 0).any() else 0
    force_ratio = up / dn if dn > 0 else np.nan
    # 近期(20日)量能 vs 长期(120日)量能 → 资金在进还是在退
    vol_recent = vol.tail(20).mean() / vol.tail(120).mean() if len(vol) >= 120 else 1
    # 量价背离: 价近60日新高 但 量未新高
    price_hi = close.tail(60).max() >= close.max() * 0.99
    vol_at_hi = vol.tail(5).mean()
    vol_prev_hi = vol.tail(60).max()
    divergence = bool(price_hi and vol_at_hi < vol_prev_hi * 0.9)
    force = ('强' if force_ratio > 1.15 and vol_recent >= 1.0 else
             '弱' if force_ratio < 0.9 or vol_recent < 0.8 else '中')

    # ===== 2. 位置: 在趋势的哪一段 =====
    lo = low.min(); hi = high.max()
    from_low = (last / lo - 1) * 100 if lo > 0 else np.nan
    from_high = (last / hi - 1) * 100 if hi > 0 else np.nan
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    ma120 = close.rolling(120).mean().iloc[-1] if len(close) >= 120 else ma60
    bull_align = ma20 > ma60 > ma120
    # 阶段判定
    if from_low < 30 and from_high < -25:
        stage = '起步(低位)'
    elif bull_align and from_high > -15 and from_low < 150:
        stage = '主升(趋势中)'
    elif from_low > 150 or (from_high > -8 and from_low > 80):
        stage = '高位(追高风险)'
    elif divergence:
        stage = '衰竭(背离)'
    else:
        stage = '震荡/不明'

    # ===== 3. 博弈: 筹码成本 + 谁在买 =====
    # 筹码成本近似 = 250日 成交量加权均价(VWAP)
    vwap = float((close * vol).sum() / vol.sum()) if vol.sum() > 0 else last
    profit_ratio = (last / vwap - 1) * 100          # 现价相对平均成本
    turnover = df['turnover'].tail(60).mean() if 'turnover' in df.columns else np.nan
    # 市值
    mktcap = np.nan
    if 'outstanding_share' in df.columns:
        mktcap = float(last * df['outstanding_share'].iloc[-1] / 1e8)
    # 个股 vs 行业 背离(游资真正的签名: 行业没动, 个股独立走强=题材)
    ind_div = np.nan
    if industry_df is not None and len(industry_df) > 250:
        indf = industry_df.copy()
        indf['date'] = pd.to_datetime(indf['date'])
        if asof:
            indf = indf[indf['date'] <= pd.Timestamp(asof)]
        indf = indf.sort_values('date')
        if len(indf) > 250:
            ic = indf['close']
            ind_ret1y = (ic.iloc[-1] / ic.iloc[-250] - 1) * 100
            stk_ret1y = (last / close.iloc[0] - 1) * 100 if len(close) > 1 else 0
            # 用同样窗口: 个股近250日
            stk_ret1y = (last / df['close'].iloc[max(0, len(df)-250)] - 1) * 100
            ind_div = stk_ret1y - ind_ret1y

    # 判定博弈结构(背离需结合市值: 大盘背离=龙头领先(好); 中小盘背离=题材(坏))
    big = (mktcap == mktcap and mktcap >= 800)   # 大盘: 背离是龙头领先
    if ind_div == ind_div and ind_div > 20 and not big:
        game = '题材(背离行业%.0fpp)' % ind_div
    elif ind_div == ind_div and ind_div > 20 and big:
        game = '龙头领先(背离%.0fpp)' % ind_div    # 大盘股跑赢行业 = 正常, 不否决
    elif mktcap == mktcap and mktcap < 300 and turnover > 6:
        game = '游资(小盘高换手)'
    elif mktcap == mktcap and mktcap > 500 and turnover < 5:
        game = '机构(大盘低换手)'
    elif profit_ratio > 30:
        game = '获利盘厚(易出货)'
    else:
        game = '混合'

    # ===== 4. 节奏: 回调健不健康 =====
    # 近20日回调深度 + 回调段量能 vs 上涨段量能
    seg = df.tail(40)
    r20 = (last / close.iloc[-21] - 1) * 100 if len(close) > 21 else np.nan
    up_seg = seg.loc[seg['close'].pct_change() > 0, 'volume'].mean()
    dn_seg = seg.loc[seg['close'].pct_change() < 0, 'volume'].mean()
    pullback_shrink = dn_seg / up_seg if up_seg and up_seg > 0 else np.nan
    if r20 < -5 and pullback_shrink < 1:
        rhythm = '健康回调(缩量)'
    elif r20 < -8 and pullback_shrink > 1.1:
        rhythm = '放量下跌(危险)'
    elif r20 > 20:
        rhythm = '短期过热'
    else:
        rhythm = '平稳'

    # ===== 否决规则(只拦大坑, 不预测收益) =====
    veto = []
    if stage == '高位(追高风险)':
        veto.append('位置高(距低点%.0f%%)' % from_low)
    if divergence:
        veto.append('量价背离(拉升无量)')
    if game.startswith('游资') or game.startswith('题材'):
        veto.append('游资/题材结构(%s)' % game)
    if rhythm == '放量下跌(危险)':
        veto.append('放量破位')
    if profit_ratio > 40:
        veto.append('获利盘过厚(%.0f%%)' % profit_ratio)

    return {
        '力量': force, '力量比': round(force_ratio, 2) if force_ratio == force_ratio else None,
        '位置': stage, '距低点%': round(from_low, 0) if from_low == from_low else None,
        '距高点%': round(from_high, 1) if from_high == from_high else None,
        '博弈': game, '现价/成本%': round(profit_ratio, 1) if profit_ratio == profit_ratio else None,
        '节奏': rhythm, '量价背离': divergence,
        '市值亿': round(mktcap, 0) if mktcap == mktcap else None,
        '个股vs行业pp': round(ind_div, 1) if ind_div == ind_div else None,
        '换手%': round(turnover, 1) if turnover == turnover else None,
        '否决': len(veto) > 0, '理由': veto,
    }


def load(code):
    from src.data_loader import DataLoader
    df = DataLoader().load_cache(str(code).zfill(6))
    return df


def load_industry_of(code):
    """该股的同花顺行业指数(用于算个股vs行业背离)"""
    try:
        tm = pd.read_csv(os.path.join(DATA_DIR, 'ths_stock_industry.csv'), dtype={'code': str})
        tm['code'] = tm['code'].str.zfill(6)
        row = tm[tm['code'] == str(code).zfill(6)]
        if len(row) == 0:
            return None
        ind = row['industry'].iloc[0]
        fp = os.path.join(DATA_DIR, 'ths_industry_index', f'{ind}.csv')
        if not os.path.exists(fp):
            return None
        d = pd.read_csv(fp, parse_dates=['日期']).rename(columns={'收盘价': 'close'})
        return d[['日期', 'close']].rename(columns={'日期': 'date'})
    except Exception:
        return None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', default=None)
    ap.add_argument('--compare', default=None, help='逗号分隔多个代码')
    ap.add_argument('--asof', default=None)
    args = ap.parse_args()

    codes = (args.compare.split(',') if args.compare
             else [args.code] if args.code else ['601118', '300308', '300364'])
    names = {'601118': '海南橡胶', '300308': '中际旭创', '300364': '中文在线'}
    for c in codes:
        c = c.strip().zfill(6)
        df = load(c)
        if df is None:
            print(f'{c}: 无数据'); continue
        r = analyze(df, args.asof, industry_df=load_industry_of(c))
        if r is None:
            print(f'{c}: 数据不足'); continue
        flag = '✗ 否决' if r['否决'] else '○ 通过'
        print(f"\n{names.get(c, c)}({c})  {flag}")
        print(f"  力量={r['力量']}(比{r['力量比']})  位置={r['位置']}(距低{r['距低点%']}% 距高{r['距高点%']}%)")
        print(f"  博弈={r['博弈']}(现价/成本{r['现价/成本%']}% 市值{r['市值亿']}亿 换手{r['换手%']}% 个股vs行业{r['个股vs行业pp']}pp)")
        print(f"  节奏={r['节奏']}  量价背离={r['量价背离']}")
        if r['理由']:
            print(f"  否决理由: {', '.join(r['理由'])}")


if __name__ == '__main__':
    main()
