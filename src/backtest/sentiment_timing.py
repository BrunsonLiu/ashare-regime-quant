# -*- coding: utf-8 -*-
"""
情绪择时回测 —— 最小化验证"冰点反转"假说
=========================================
假说来源: markers.json 统计冰点后3日涨停数回升率75%, 但那是"涨停数"维度,
不代表价格赚钱。本实验在指数层面回答唯一问题: 冰点后买入, 价格上是否占优。

实验纪律(与回测引擎同一套反前视标准):
- 分位数阈值用扩展窗口(每日只用≤T数据), 不用全样本分位
- 情绪数据T日收盘后才可知 → T+1开盘成交, 绝不当天买
- 含费用: 佣金万2.5双边 + 滑点千1双边(指数ETF无印花税)
- 全部变体一起报告, 不挑最好的说(防变体钓鱼)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR

COMMISSION = 0.00025   # 单边
SLIPPAGE = 0.001       # 单边
WARMUP = 120           # 扩展分位数预热期(约半年)
COST_ROUNDTRIP = 2 * (COMMISSION + SLIPPAGE)


def load_data(index_code='000001'):
    """情绪日线 + 指数, 按日期对齐"""
    s = pd.read_csv(os.path.join(DATA_DIR, 'sentiment_3y.csv'))
    s['date'] = pd.to_datetime(s['date'])
    s = s.sort_values('date').reset_index(drop=True)

    idx_path = os.path.join(DATA_DIR, f'index_{index_code}.csv')
    if not os.path.exists(idx_path):
        raise FileNotFoundError(f'缺少指数缓存 {idx_path}, 请先运行会拉取该指数的命令')
    idx = pd.read_csv(idx_path, parse_dates=['date'])
    idx = idx.sort_values('date').reset_index(drop=True)

    df = s.merge(idx[['date', 'open', 'close']], on='date', how='inner')
    if len(df) < 300:
        raise RuntimeError(f'情绪与指数重叠不足: {len(df)} 天')
    return df


def expanding_thresholds(df):
    """扩展窗口分位数: 第t行的阈值只由[0..t]计算(预热期内为NaN, 不出信号)"""
    p20_zt, p80_zr, p50_zt = [], [], []
    zt = df['zt_count'].values
    zr = df['zhaban_rate'].values
    for t in range(len(df)):
        if t < WARMUP:
            p20_zt.append(np.nan); p80_zr.append(np.nan); p50_zt.append(np.nan)
            continue
        p20_zt.append(np.quantile(zt[:t + 1], 0.20))
        p80_zr.append(np.quantile(zr[:t + 1], 0.80))
        p50_zt.append(np.quantile(zt[:t + 1], 0.50))
    df = df.copy()
    df['p20_zt'] = p20_zt
    df['p80_zr'] = p80_zr
    df['p50_zt'] = p50_zt
    df['is_ice'] = ((df['zt_count'] < df['p20_zt']) |
                    (df['zhaban_rate'] > df['p80_zr'])).astype(int)
    return df


def _open_map(idx_df):
    return dict(zip(idx_df['date'], idx_df['open']))


def _equity_curve(df, trades):
    """按日净值: 持仓日跟随指数, 空仓为现金(简化, 用于回撤统计)"""
    equity = pd.Series(1.0, index=df['date'].values)
    if not trades:
        return equity
    in_pos = np.zeros(len(df), dtype=bool)
    date_pos = {t['entry_date']: t['exit_date'] for t in trades}
    dates = df['date'].values
    for i, d in enumerate(dates):
        for t in trades:
            if t['entry_date'] <= d <= t['exit_date']:
                in_pos[i] = True
                break
    curve = 1.0
    rets = df['close'].pct_change().fillna(0).values
    for i in range(len(df)):
        if in_pos[i]:
            curve *= (1 + rets[i])
        equity.iloc[i] = curve
    return equity


def run_fixed_hold(df, hold_days, require_consecutive_ice=1, label=''):
    """固定持有N日: 冰点日T收盘出信号, T+1开盘买入, T+1+N开盘卖出"""
    dates = df['date'].tolist()
    opens = df['open'].values
    n = len(df)
    trades = []
    busy_until = -1
    ice = df['is_ice'].values

    for t in range(WARMUP, n):
        if not ice[t]:
            continue
        # 连续冰点确认: 需要前 require_consecutive_ice-1 天也是冰点
        if require_consecutive_ice > 1:
            if t - (require_consecutive_ice - 1) < 0:
                continue
            if not all(ice[t - k] for k in range(1, require_consecutive_ice)):
                continue
        entry_i = t + 1
        exit_i = t + 1 + hold_days
        if entry_i >= n:
            continue
        if entry_i <= busy_until:
            continue  # 持仓中, 忽略重叠信号
        exit_price_i = min(exit_i, n - 1)
        entry_px = opens[entry_i] * (1 + SLIPPAGE)
        exit_px = opens[exit_price_i] * (1 - SLIPPAGE)
        ret = exit_px / entry_px - 1 - COST_ROUNDTRIP
        trades.append({
            'signal_date': dates[t], 'entry_date': dates[entry_i],
            'exit_date': dates[exit_price_i], 'ret': ret,
            'forced': exit_i >= n,
        })
        busy_until = exit_price_i
    return trades


def run_recovery_exit(df, max_hold=15):
    """情绪修复退出: 冰点后买入, 涨停数回到扩展P50之上卖出, 最多持有max_hold日"""
    dates = df['date'].tolist()
    opens = df['open'].values
    zt = df['zt_count'].values
    p50 = df['p50_zt'].values
    n = len(df)
    trades = []
    busy_until = -1
    ice = df['is_ice'].values

    for t in range(WARMUP, n):
        if not ice[t]:
            continue
        entry_i = t + 1
        if entry_i >= n or entry_i <= busy_until:
            continue
        exit_i = None
        for k in range(entry_i + 1, min(entry_i + max_hold + 1, n)):
            if not np.isnan(p50[k]) and zt[k] >= p50[k]:
                exit_i = k  # 修复日收盘确认 → 次日开盘卖
                exit_i = min(k + 1, n - 1)
                break
        if exit_i is None:
            exit_i = min(entry_i + max_hold, n - 1)
        entry_px = opens[entry_i] * (1 + SLIPPAGE)
        exit_px = opens[exit_i] * (1 - SLIPPAGE)
        ret = exit_px / entry_px - 1 - COST_ROUNDTRIP
        trades.append({
            'signal_date': dates[t], 'entry_date': dates[entry_i],
            'exit_date': dates[exit_i], 'ret': ret,
            'forced': False,
        })
        busy_until = exit_i
    return trades


def summarize(df, trades, label):
    eq = _equity_curve(df, trades)
    if trades:
        rets = [t['ret'] for t in trades]
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        total = float(np.prod([1 + r for r in rets]) - 1)
        dd = float(((eq / eq.cummax()) - 1).min())
        avg = float(np.mean(rets)); med = float(np.median(rets))
        worst = float(np.min(rets))
        exposure = float(eq.diff().ne(0).mean() * 100)
    else:
        win = total = avg = med = worst = dd = 0.0
        rets = []
    # 同期买入持有基准(从首个信号到末日)
    bh = float(df['close'].iloc[-1] / df['close'].iloc[WARMUP] - 1)
    return {
        'variant': label, 'trades': len(trades), 'win%': round(win, 1),
        'avg%': round(avg * 100, 2), 'median%': round(med * 100, 2),
        'total%': round(total * 100, 2), 'maxDD%': round(dd * 100, 2),
        'worst%': round(worst * 100, 2), 'B&H%': round(bh * 100, 2),
    }, trades


def run_all(index_code='000001', save=True):
    df = expanding_thresholds(load_data(index_code))
    ice_days = int(df['is_ice'].sum())
    print(f'样本: {len(df)}天 (预热{WARMUP}天), 冰点日(扩展分位): {ice_days}天')
    print(f'费用: 单边佣金{COMMISSION*10000:.0f}%% + 滑点{SLIPPAGE*1000:.0f}‰, '
          f'往返约{COST_ROUNDTRIP*100:.2f}%%\n')

    variants = [
        (lambda d: run_fixed_hold(d, 1), '冰点→持有1日'),
        (lambda d: run_fixed_hold(d, 3), '冰点→持有3日'),
        (lambda d: run_fixed_hold(d, 5), '冰点→持有5日'),
        (lambda d: run_fixed_hold(d, 10), '冰点→持有10日'),
        (lambda d: run_fixed_hold(d, 5, require_consecutive_ice=2), '连续2日冰点→持有5日'),
        (lambda d: run_recovery_exit(d), '冰点→情绪修复退出(≤15日)'),
    ]

    all_trades = {}
    rows = []
    for fn, label in variants:
        summary, trades = summarize(df, fn(df), label)
        rows.append(summary)
        all_trades[label] = trades

    res = pd.DataFrame(rows)
    print(res.to_string(index=False))
    print('\n注: B&H% = 同期(预热期后~末日)买入持有; exposure未计, maxDD为净值口径')

    if save:
        out = pd.DataFrame(
            [(v, t['signal_date'].date(), t['entry_date'].date(),
              t['exit_date'].date(), round(t['ret'] * 100, 3))
             for v, ts in all_trades.items() for t in ts],
            columns=['variant', 'signal_date', 'entry_date', 'exit_date', 'ret_pct'])
        path = os.path.join(DATA_DIR, 'sentiment_timing_trades.csv')
        out.to_csv(path, index=False, encoding='utf-8-sig')
        print(f'\n[OK] 交易明细 → {path} ({len(out)}笔)')
    return res


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--index', default='000001', help='指数代码(需有缓存)')
    ap.add_argument('--no-save', action='store_true')
    args = ap.parse_args()
    run_all(index_code=args.index, save=not args.no_save)
