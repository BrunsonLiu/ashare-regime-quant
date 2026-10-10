# -*- coding: utf-8 -*-
"""
守则策略(统一引擎) —— daily 建议 与 回测 用同一套逻辑
========================================================
修复裂缝: 此前 daily 用"强势行业+市值龙头+结构关", 而 main.py backtest 仍用
已证伪的"19因子打分前20%" —— 回测无法验证 daily。

本模块是**唯一权威定义**, 双方都调用它:

  ① 环境:   A主线(滞后确认: 进3退2)   —— 不是就不持有
  ② 行业:   同花顺行业指数, 有前景(近1y>0且近3y>0) 且 不接盘(距高点-3%~-35%,近20日<15%)
  ③ 个股:   该行业**市值**龙头(时点市值, 剔除炒作票)
  ④ 结构:   力量/位置/博弈/节奏 过关(否决 高位/背离/题材/放量破位)
  ⑤ 节奏:   月频调仓; -15%止损

时点正确(PIT): 选行业/选龙头/结构判定 全部只用 ≤asof 的数据。

用法: python -m src.strategy.guardian            # 当前建议
      python -m src.strategy.guardian --backtest # 回测(分段+逐年)
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR, RISK_CONFIG
from src.data_loader import DataLoader

COMMISSION = 0.00025
STAMP_TAX = 0.0005
SLIPPAGE = 0.001
STOP_LOSS = abs(RISK_CONFIG.get('stop_loss', -0.15))
REBAL = 'monthly'


# ==================== 数据 ====================

def _load_prices(codes):
    loader = DataLoader()
    out = {}
    for c in codes:
        df = loader.load_cache(c)
        if df is None or len(df) < 120:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        cols = [x for x in ('open', 'high', 'low', 'close', 'volume', 'turnover',
                            'outstanding_share') if x in df.columns]
        out[c] = df.set_index('date')[cols]
    return out


def _ths_map():
    """股票→同花顺行业"""
    fp = os.path.join(DATA_DIR, 'ths_stock_industry.csv')
    if not os.path.exists(fp):
        return {}
    tm = pd.read_csv(fp, dtype={'code': str})
    tm['code'] = tm['code'].str.zfill(6)
    return dict(zip(tm['code'], tm['industry']))


def _industry_index(industry):
    fp = os.path.join(DATA_DIR, 'ths_industry_index', f'{industry}.csv')
    if not os.path.exists(fp):
        return None
    d = pd.read_csv(fp, parse_dates=['日期']).rename(
        columns={'开盘价': 'open', '最高价': 'high', '最低价': 'low', '收盘价': 'close'})
    return d.set_index('日期')


# ==================== ② 选行业(有前景 + 不接盘) ====================

def _industry_score(ind_df, asof):
    d = ind_df[ind_df.index <= pd.Timestamp(asof)] if asof else ind_df
    if len(d) < 260:
        return None
    c = d['close']; hi = d['high']; last = c.iloc[-1]
    r1 = (last / c.iloc[-250] - 1) * 100 if len(c) > 250 else None
    r3 = (last / c.iloc[-750] - 1) * 100 if len(c) > 750 else None
    r20 = (last / c.iloc[-21] - 1) * 100 if len(c) > 21 else None
    dd = (last / hi.iloc[-250:].max() - 1) * 100
    future = (r1 is not None and r1 > 0) and (r3 is not None and r3 > 0)
    no_chase = (-35 <= dd <= -3) and (r20 is not None and r20 < 15)
    return {'近1年%': r1, '近3年%': r3, '距高点%': dd, '近20日%': r20,
            '有前景': future, '不接盘': no_chase, '入选': future and no_chase}


def select_industries(asof=None, top_n=5, require_position=True):
    """返回入选行业列表(有前景 + 不接盘), 按近1年排序"""
    fp = os.path.join(DATA_DIR, 'ths_industries.csv')
    if not os.path.exists(fp):
        return []
    names = pd.read_csv(fp)['name'].tolist()
    picked = []
    for name in names:
        idx = _industry_index(name)
        if idx is None:
            continue
        s = _industry_score(idx, asof)
        if s and s['有前景'] and (s['不接盘'] or not require_position):
            picked.append((name, s['近1年%']))
    picked.sort(key=lambda x: -x[1])
    return [p[0] for p in picked[:top_n]]


# ==================== ③ 选个股(时点市值龙头 + 剔除炒作) ====================

def _mktcap_at(df, asof):
    if 'outstanding_share' not in df.columns:
        return None
    d = df[df.index <= pd.Timestamp(asof)] if asof else df
    if len(d) == 0:
        return None
    last = d.iloc[-1]
    if pd.isna(last['close']) or pd.isna(last['outstanding_share']):
        return None
    return float(last['close'] * last['outstanding_share'] / 1e8)


def _is_speculative(df, asof, max_turnover=6.0):
    """炒作票: 高换手 + 净涨跌平庸"""
    d = df[df.index <= pd.Timestamp(asof)].tail(250) if asof else df.tail(250)
    if len(d) < 60:
        return False
    tr = d['turnover'].mean() if 'turnover' in d.columns else 0
    ret = (d['close'].iloc[-1] / d['close'].iloc[0] - 1) * 100 if len(d) > 1 else 0
    return (tr > max_turnover) and (ret < 10)


def select_stocks(industries, data, ths_map, asof=None, per_ind=3,
                  use_structure=True, max_total=15):
    """行业内的时点市值龙头; use_structure=True 时再过结构关"""
    picked = []
    for ind in industries:
        cands = [(c, _mktcap_at(df, asof)) for c, df in data.items()
                 if ths_map.get(c) == ind]
        cands = [(c, mc) for c, mc in cands if mc is not None and not _is_speculative(data[c], asof)]
        cands.sort(key=lambda x: -x[1])
        n = 0
        for c, mc in cands:
            if n >= per_ind:
                break
            if use_structure:
                st = _structure(data[c], asof, c)
                if st and st['否决']:
                    continue
            picked.append(c); n += 1
    return picked[:max_total]


_STRUCT_CACHE = {}


def _structure(df, asof=None, code=None):
    """单只结构画像(带缓存)。df 为 date 索引; 需重置为 date 列供 analyze 用。"""
    key = (code, str(asof) if asof else None)
    if asof is None and key in _STRUCT_CACHE:
        return _STRUCT_CACHE[key]
    try:
        from src.utils.market_structure import analyze, load_industry_of
        d = df.reset_index()
        d = d.rename(columns={d.columns[0]: 'date'})
        if code:
            d['code'] = code
        ind_df = load_industry_of(code) if code else None
        r = analyze(d, asof, industry_df=ind_df)
        if r is not None and '否决' not in r:   # analyze 返回中文键'否决'
            r = None
    except Exception:
        r = None
    if asof is None:
        _STRUCT_CACHE[key] = r
    return r


# ==================== ① 环境(滞后确认) ====================

def env_confirmed(asof=None, index_days=1400):
    from src.utils.market_env import MarketEnvironment, load_sentiment, hysteresis_confirm
    loader = DataLoader()
    idx = loader.get_index_data('000001', days=index_days)  # 需覆盖回测全窗口
    if idx is None or len(idx) == 0:
        return None
    idx['date'] = pd.to_datetime(idx['date'])
    envs, _ = MarketEnvironment().classify_series(idx, load_sentiment())
    conf = hysteresis_confirm(envs, enter_n=3, exit_n=2, target='A')
    if asof:
        conf = conf[conf.index <= pd.Timestamp(asof)]
    return conf


# ==================== 回测 ====================

def backtest(data, ths_map, gate, use_structure=True, require_position=True,
             stop=STOP_LOSS, monthly=True, cost=True):
    dates = sorted(set().union(*[set(d.index) for d in data.values()]))
    if len(dates) == 0:
        return None
    dates = [d for d in dates if d >= pd.Timestamp('2023-09-08')]
    cash, holdings = 1.0, {}
    equity, n_trades, last_key = [], 0, None
    stop = abs(stop) if stop else None

    def px(c, day, w='close'):
        d = data.get(c)
        if d is None or day not in d.index:
            return None
        v = d.loc[day, w]
        return float(v) if pd.notna(v) else None

    def val(day):
        v = cash
        for c, h in holdings.items():
            p = px(c, day)
            v += h['sh'] * (p if p is not None else h['cost'])
        return v

    for i, day in enumerate(dates):
        in_mkt = bool(gate.get(day, False))
        if stop and i > 0:
            for c in list(holdings):
                pcl = px(c, dates[i-1])
                if pcl and pcl / holdings[c]['cost'] - 1 <= -stop:
                    pop = px(c, day, 'open') or pcl
                    pr = holdings[c]['sh'] * pop
                    cash += pr - (pr * (COMMISSION+STAMP_TAX+SLIPPAGE) if cost else 0)
                    n_trades += 1; del holdings[c]
        key = (day.year, day.month) if monthly else day
        if key != last_key:
            last_key = key
            total = val(day)
            targets = []
            if in_mkt:
                inds = select_industries(day, require_position=require_position)
                targets = select_stocks(inds, data, ths_map, asof=day,
                                        use_structure=use_structure)
            targets = set(targets)
            for c in list(holdings):
                if c not in targets:
                    p = px(c, day, 'open') or px(c, day)
                    if p:
                        pr = holdings[c]['sh'] * p
                        cash += pr - (pr * (COMMISSION+STAMP_TAX+SLIPPAGE) if cost else 0)
                        n_trades += 1; del holdings[c]
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
    ap = argparse.ArgumentParser()
    ap.add_argument('--backtest', action='store_true')
    args = ap.parse_args()

    ths_map = _ths_map()
    codes = list(ths_map.keys())
    data = _load_prices(codes)
    gate = env_confirmed()
    print(f'universe {len(data)}只(有行情), THS行业 {len(set(ths_map.values()))}个')

    inds = select_industries()
    print(f'\n入选行业(有前景+不接盘): {inds}')
    stocks = select_stocks(inds, data, ths_map)
    print(f'候选个股({len(stocks)}只):')
    for c in stocks:
        print(f'  {c} {ths_map.get(c)}')

    if args.backtest:
        print('\n=== 回测(环境闸门+月频+-15%止损) ===')
        # 基准
        closes = pd.DataFrame({c: d['close'] for c, d in data.items()}).sort_index()
        closes = closes[closes.index >= pd.Timestamp('2023-09-08')]
        bh = (1 + closes.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
        print(f'基准-等权持有全部: {(bh.iloc[-1]-1)*100:+.1f}% / 回撤{((bh/bh.cummax())-1).min()*100:.1f}%')
        for label, us, rp in [('守则(含结构关)', True, True), ('守则(无结构关)', False, True)]:
            r = backtest(data, ths_map, gate, use_structure=us, require_position=rp)
            print(f'  {label:18} 收益{r["ret"]:+7.1f}% 回撤{r["dd"]:6.1f}% 交易{r["trades"]}')
        # 分段
        print('\n分段:')
        r = backtest(data, ths_map, gate)
        eq = r['eq']
        for k, seg in enumerate(np.array_split(eq.index, 3)):
            e = eq.loc[seg]
            print(f'  段{k+1} {seg[0].date()}~{seg[-1].date()}: {(e.iloc[-1]/e.iloc[0]-1)*100:+.1f}%')


if __name__ == '__main__':
    main()
