# -*- coding: utf-8 -*-
"""
跨周期验证 —— 守则核心条款的12年检验
======================================
覆盖 2014-03 ~ 2026-09(多轮完整牛熊): 2015股灾 / 2016熔断 / 2018贸易战熊 /
2019-21结构牛 / 2022熊 / 2024反弹。

检验守则最核心的纯指数规则(无参数拟合):
  "熊市空仓": MA20 < MA60×0.98 且近20日跌 > 4% → 空仓观望

用法: python -m src.backtest.cross_cycle
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from src.data_loader import DataLoader

MA_SHORT, MA_LONG = 20, 60
BEAR_DROP = -0.04
BEAR_MA_RATIO = 0.98


def bear_mask(close):
    """守则熊市判定(纯指数)"""
    ma_s = close.rolling(MA_SHORT).mean()
    ma_l = close.rolling(MA_LONG).mean()
    ret20 = close.pct_change(20)
    return (ma_s < ma_l * BEAR_MA_RATIO) & (ret20 < BEAR_DROP)


def run(index_code='000001', days=4600):
    df = DataLoader().get_index_data(index_code, days=days)
    if df is None or len(df) < 500:
        raise RuntimeError('指数长历史不足(需先拉长指数缓存)')
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()
    close = df['close']
    ret = close.pct_change()
    bear = bear_mask(close)

    eq_hold = (1 + ret).cumprod()
    eq_bear_out = (1 + ret.where(~bear, 0)).cumprod()
    return {
        'start': close.index[0], 'end': close.index[-1], 'n_days': len(close),
        'bear_days': int(bear.sum()), 'bear_pct': round(bear.mean() * 100, 1),
        'hold_ret': round((eq_hold.iloc[-1] - 1) * 100, 1),
        'hold_dd': round(((eq_hold / eq_hold.cummax()) - 1).min() * 100, 1),
        'bear_out_ret': round((eq_bear_out.iloc[-1] - 1) * 100, 1),
        'bear_out_dd': round(((eq_bear_out / eq_bear_out.cummax()) - 1).min() * 100, 1),
        'yearly': _yearly(close.index, ret, bear),
    }


def _yearly(index, ret, bear):
    rows = []
    for y in sorted(set(index.year)):
        m = index.year == y
        yr = (1 + ret[m]).prod() - 1
        bm = bear & m
        br = (1 + ret[bm]).prod() - 1 if bm.sum() > 0 else 0.0
        rows.append({'year': y, 'ret_pct': round(yr * 100, 1),
                     'bear_days': int(bm.sum()), 'bear_ret_pct': round(br * 100, 1)})
    return rows


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    r = run()
    print(f'=== 跨周期验证 {r["start"].date()} ~ {r["end"].date()} '
          f'({r["n_days"]}日, {r["n_days"]/243:.1f}年) ===')
    print(f'{"年份":<6}{"指数收益":>10}{"熊市天数":>10}{"熊市期收益":>12}')
    for row in r['yearly']:
        print(f'{row["year"]:<6}{row["ret_pct"]:>9.1f}%{row["bear_days"]:>10}'
              f'{row["bear_ret_pct"]:>11.1f}%')
    print()
    print(f'全程持有:      收益{r["hold_ret"]:+.1f}%  最大回撤{r["hold_dd"]:.1f}%')
    print(f'熊市空仓(守则): 收益{r["bear_out_ret"]:+.1f}%  最大回撤{r["bear_out_dd"]:.1f}%')
    print(f'熊市天数占比: {r["bear_pct"]}%')
    return r


if __name__ == '__main__':
    main()
