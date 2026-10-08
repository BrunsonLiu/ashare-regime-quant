# -*- coding: utf-8 -*-
"""
策略乙(有前景 + 不接盘) —— 接入回测并验证
=============================================
选行业: 同花顺行业指数, 同时满足
  A. 有前景: 近1年>0 且 近3年>0
  B. 不接盘: 距250日高点 -35%~-3%, 且近20日<15%(不过热)
选个股: 该行业**市值**龙头(THS行业映射 + 市值排序), 剔除炒作票
节奏: 月频调仓; 环境A(确认)才持有; -15%止损

对照: (1)只看有前景(不加位置) (2)等权持有全市值龙头池

用法: python -m src.backtest.strategy_b
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.data_loader import DataLoader
from src.utils.market_env import MarketEnvironment, load_sentiment, hysteresis_confirm
from src.utils.industry_trend_v3 import load_index, score_industry

COMMISSION, STAMP_TAX, SLIPPAGE = 0.00025, 0.0005, 0.001
START = pd.Timestamp('2023-09-08')


def load_leaders_by_ths():
    """{同花顺行业: [(code, mktcap), ...] 按市值降序}"""
    loader = DataLoader()
    tm = pd.read_csv(os.path.join(DATA_DIR, 'ths_stock_industry.csv'), dtype={'code': str})
    tm['code'] = tm['code'].str.zfill(6)
    out = {}
    for _, r in tm.iterrows():
        df = loader.load_cache(r['code'])
        if df is None or len(df) < 120 or 'outstanding_share' not in df.columns:
            continue
        last = df.iloc[-1]
        mc = last['close'] * last['outstanding_share'] / 1e8
        out.setdefault(r['industry'], []).append((r['code'], mc))
    for k in out:
        out[k] = sorted(out[k], key=lambda x: -x[1])
    return out


def select_industries(asof, require_position=True):
    """
    截至 asof 选行业。require_position=True→乙(有前景+不接盘);
    False→只看有前景。
    """
    idx = load_index()
    picked = []
    for name, df in idx.items():
        s = score_industry(df, asof)
        if s is None:
            continue
        if s['有前景'] and (s['不接盘'] or not require_position):
            picked.append((name, s['近1年%']))
    picked.sort(key=lambda x: -x[1])
    return [p[0] for p in picked]


def load_prices(codes):
    loader = DataLoader()
    out = {}
    for c in codes:
        df = loader.load_cache(c)
        if df is None or len(df) < 100:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        out[c] = df[['open', 'close']]
    return out


def env_gate(index_df):
    env_map, _ = MarketEnvironment().classify_series(index_df, load_sentiment())
    return hysteresis_confirm(env_map, enter_n=3, exit_n=2, target='A').shift(1).ffill().fillna(False)


def backtest(asof_fn, leader_map, data, gate, gate_on=True, stop=0.15,
             hold_k=3, max_industries=5, monthly=True):
    """asof_fn(asof)->行业列表; 每期取行业市值龙头前hold_k, 等权"""
    loader = DataLoader()
    idx = loader.get_index_data('000001', days=1300); idx['date'] = pd.to_datetime(idx['date'])
    dates = sorted(set().union(*[set(d.index) for d in data.values()]))
    dates = [d for d in dates if d >= START]

    cash, holdings = 1.0, {}
    equity, n_trades = [], 0
    last_key = None

    def px(c, day, which='close'):
        d = data.get(c)
        if d is None or day not in d.index:
            return None
        v = d.loc[day, which]
        return float(v) if pd.notna(v) else None

    def val(day):
        v = cash
        for c, h in holdings.items():
            cl = px(c, day)
            v += h['sh'] * (cl if cl is not None else h['cost'])
        return v

    for i, day in enumerate(dates):
        in_mkt = bool(gate.get(day, False)) if gate_on else True
        # 止损(T-1判, T开盘成交)
        if stop and i > 0:
            for c in list(holdings):
                pcl = px(c, dates[i-1])
                if pcl and pcl / holdings[c]['cost'] - 1 <= -stop:
                    pop = px(c, day, 'open')
                    if pop:
                        pr = holdings[c]['sh'] * pop
                        cash += pr - (pr * (COMMISSION+STAMP_TAX+SLIPPAGE))
                        n_trades += 1
                        del holdings[c]
        key = (day.year, day.month) if monthly else day
        if key != last_key:
            last_key = key
            total = val(day)
            targets = []
            if in_mkt:
                inds = asof_fn(day)[:max_industries]
                for ind in inds:
                    for code, _ in leader_map.get(ind, [])[:hold_k]:
                        if code in data:
                            targets.append(code)
            targets = set(targets)
            for c in list(holdings):
                if c not in targets:
                    p = px(c, day, 'open') or px(c, day)
                    if p:
                        pr = holdings[c]['sh'] * p
                        cash += pr - (pr * (COMMISSION+STAMP_TAX+SLIPPAGE))
                        n_trades += 1
                        del holdings[c]
            if targets:
                tgt = total / len(targets)
                for c in targets:
                    p = px(c, day, 'open') or px(c, day)
                    if not p or p <= 0:
                        continue
                    cur = holdings.get(c, {}).get('sh', 0.0)
                    delta = tgt - cur * p
                    if delta <= 0:
                        continue
                    aff = min(delta, max(cash, 0))
                    if aff > 0:
                        sh = aff / p / (1 + COMMISSION + SLIPPAGE)
                        cash -= sh * p * (1 + COMMISSION + SLIPPAGE)
                        if c in holdings:
                            h = holdings[c]
                            h['cost'] = (h['cost']*h['sh'] + p*sh)/(h['sh']+sh)
                            h['sh'] += sh
                        else:
                            holdings[c] = {'sh': sh, 'cost': p}
                        n_trades += 1
        equity.append({'date': day, 'equity': val(day)})
    eq = pd.DataFrame(equity).set_index('date')['equity']
    return {'ret': round((eq.iloc[-1]-1)*100, 1),
            'dd': round(((eq/eq.cummax())-1).min()*100, 1),
            'trades': n_trades, 'eq': eq}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    leader_map = load_leaders_by_ths()
    all_codes = set(c for lst in leader_map.values() for c, _ in lst)
    data = load_prices(all_codes)
    loader = DataLoader()
    idx = loader.get_index_data('000001', days=1300); idx['date'] = pd.to_datetime(idx['date'])
    gate = env_gate(idx)
    print(f'THS行业龙头映射: {len(leader_map)}行业, {len(data)}只有行情')

    # 基准: 等权持有全部
    closes = pd.DataFrame({c: d['close'] for c, d in data.items()}).sort_index()
    closes = closes[closes.index >= START]
    bh = (1 + closes.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
    print(f'\n基准-等权持有全部龙头: {(bh.iloc[-1]-1)*100:+.1f}% / 回撤{((bh/bh.cummax())-1).min()*100:.1f}%')

    print('\n=== 策略对比(2023-09~2026-09, 月频, -15%止损, 只做A确认) ===')
    for label, fn in [
        ('乙: 有前景+不接盘', lambda d: select_industries(d, True)),
        ('甲2: 只看有前景', lambda d: select_industries(d, False)),
    ]:
        r = backtest(fn, leader_map, data, gate, gate_on=True)
        print(f'  {label:20} 收益{r["ret"]:+7.1f}% 回撤{r["dd"]:6.1f}% 交易{r["trades"]}')
    # 不加环境闸门(纯选行业)
    r = backtest(lambda d: select_industries(d, True), leader_map, data, gate, gate_on=False)
    print(f'  {"乙(不择时, 只选行业)":20} 收益{r["ret"]:+7.1f}% 回撤{r["dd"]:6.1f}% 交易{r["trades"]}')


if __name__ == '__main__':
    main()
