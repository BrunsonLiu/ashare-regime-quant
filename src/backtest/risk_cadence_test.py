# -*- coding: utf-8 -*-
"""
止损参数 & 调仓节拍 —— 用正确的逐股模拟评估(修正近似法陷阱)
================================================================
上次的错误: "单日跌幅超阈值→该只收益记0" = 凭空抹掉亏损 → 假收益。
本模块正确做法:
  - 逐股跟踪持仓; 用 T-1 收盘判断是否触发止损
  - 触发后按 **T 日开盘价** 真实成交(承受跳空, 不抹掉亏损)
  - 环境闸门: 只在确认的A环境持有; 换手计成本

评估: #5 止损阈值 {-7%, -15%, 无} × #6 调仓节拍 {每日, 月度, 季度}

用法: python -m src.backtest.risk_cadence_test
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.data_loader import DataLoader
from src.utils.market_env import MarketEnvironment, load_sentiment, hysteresis_confirm

COMMISSION, STAMP_TAX, SLIPPAGE = 0.00025, 0.0005, 0.001
START = pd.Timestamp('2023-09-08')


def load_data(pool_file='stock_pool_leaders_mc.csv'):
    loader = DataLoader()
    pool = pd.read_csv(os.path.join(DATA_DIR, pool_file), dtype={'code': str})
    pool['code'] = pool['code'].str.zfill(6)
    data = {}
    for c in pool['code']:
        df = loader.load_cache(c)
        if df is None or len(df) < 100:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        data[c] = df[['close', 'open']]
    return data


def env_gate(index_df):
    """确认后的A环境(T-1), 返回 {date: bool}"""
    env_map, _ = MarketEnvironment().classify_series(index_df, load_sentiment())
    conf = hysteresis_confirm(env_map, enter_n=3, exit_n=2, target='A')
    return conf.shift(1).ffill().fillna(False)


def backtest(data, gate, stop_pct=None, cadence='monthly', cost=True):
    """
    stop_pct: 止损阈值(如0.07=跌破成本7%止损); None=不止损
    cadence: 'daily'/'monthly'/'quarterly' 调仓节拍
    持仓: gate=True时等权持有全部池内股票
    """
    dates = sorted(set().union(*[set(d.index) for d in data.values()]))
    dates = [d for d in dates if d >= START]
    codes = list(data.keys())
    cash, holdings = 1.0, {}   # {code: {sh, cost}}
    equity, trades = [], 0
    last_rebal_key = None

    def px(code, day):
        d = data.get(code)
        if d is None or day not in d.index:
            return None, None
        return (float(d.loc[day, 'close']), float(d.loc[day, 'open']))

    def value(day):
        v = cash
        for c, h in holdings.items():
            cl, _ = px(c, day)
            if cl is not None:
                v += h['sh'] * cl
            else:
                v += h['sh'] * h['cost']
        return v

    for i, day in enumerate(dates):
        in_mkt = bool(gate.get(day, False))

        # --- 止损检查(T-1收盘判, T开盘成交) ---
        if stop_pct and i > 0:
            prev = dates[i - 1]
            for c in list(holdings):
                pcl, _ = px(c, prev)
                if pcl is None:
                    continue
                if pcl / holdings[c]['cost'] - 1 <= -stop_pct:
                    _, pop = px(c, day)
                    if pop is not None and pop > 0:
                        proceeds = holdings[c]['sh'] * pop
                        fee = proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0
                        cash += proceeds - fee
                        trades += 1
                        del holdings[c]

        # --- 调仓节拍 ---
        if cadence == 'daily':
            key = day
        elif cadence == 'monthly':
            key = (day.year, day.month)
        else:
            key = (day.year, (day.month - 1) // 3)
        do_rebal = (key != last_rebal_key)
        if do_rebal:
            last_rebal_key = key
            total = value(day)
            targets = set(codes) if in_mkt else set()
            # 卖出不在目标
            for c in list(holdings):
                if c not in targets:
                    _, pop = px(c, day)
                    cl, _ = px(c, day)
                    p = pop if pop is not None else cl
                    if p:
                        proceeds = holdings[c]['sh'] * p
                        fee = proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0
                        cash += proceeds - fee
                        trades += 1
                        del holdings[c]
            # 买入目标(等权)
            if targets:
                tgt = total / len(targets)
                for c in targets:
                    cl, pop = px(c, day)
                    p = pop if pop is not None else cl
                    if p is None or p <= 0:
                        continue
                    cur = holdings.get(c, {}).get('sh', 0.0)
                    delta = tgt - cur * p
                    if delta <= 0:
                        continue
                    afford = min(delta, max(cash, 0))
                    if afford > 0:
                        fr = (COMMISSION + SLIPPAGE) if cost else 0
                        sh = afford / p / (1 + fr)
                        cash -= sh * p * (1 + fr)
                        if c in holdings:
                            h = holdings[c]
                            h['cost'] = (h['cost'] * h['sh'] + p * sh) / (h['sh'] + sh)
                            h['sh'] += sh
                        else:
                            holdings[c] = {'sh': sh, 'cost': p}
                        trades += 1

        equity.append({'date': day, 'equity': value(day)})

    eq = pd.DataFrame(equity).set_index('date')['equity']
    return {'ret_pct': round((eq.iloc[-1] - 1) * 100, 1),
            'max_dd_pct': round(((eq / eq.cummax()) - 1).min() * 100, 1),
            'n_trades': trades, 'eq': eq}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    data = load_data()
    loader = DataLoader()
    idx = loader.get_index_data('000001', days=1300); idx['date'] = pd.to_datetime(idx['date'])
    gate = env_gate(idx)
    print(f'universe {len(data)}只(市值龙头池), 只做A(确认)')

    print('\n=== 止损阈值 × 调仓节拍 (正确逐股模拟, T+1开盘成交, 含成本) ===')
    rows = []
    for cad in ('daily', 'monthly', 'quarterly'):
        for sl in (0.07, 0.15, None):
            r = backtest(data, gate, stop_pct=sl, cadence=cad)
            rows.append({'节拍': cad, '止损': f'{int(sl*100)}%' if sl else '无',
                         '收益%': r['ret_pct'], '回撤%': r['max_dd_pct'], '交易': r['n_trades']})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print('\n对照: 全程持有龙头池(不含环境闸门, 仅参考)')

    out = os.path.join(DATA_DIR, 'experiments', f'risk_cadence_{pd.Timestamp.now():%Y%m%d_%H%M}.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f'\n[OK] → {out}')


if __name__ == '__main__':
    main()
