# -*- coding: utf-8 -*-
"""
策略模拟持仓回放 —— "如果按守则策略执行, 现在应该持有什么"
==============================================================
回放已验证策略(STRATEGY_CONCLUSION.md):
  滚动龙头池(每年初用截至当时的成交额选龙头) + 只在A环境持有 + 等权

输出:
  - 当前持仓(代码/名称/行业/买入日/买入价/现价/浮盈/权重)
  - 交易记录(池变动 + 环境切换产生的买卖, 含盈亏)
  - 净值曲线与汇总

无前视: 选池用截至当时数据; 环境用T-1判定; 成交按当日收盘+成本(简化)。
⚠ 幸存者偏差: universe为今日现存股票。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.utils.market_env import MarketEnvironment, load_sentiment, hysteresis_confirm
from src.data_loader import DataLoader

COMMISSION, STAMP_TAX, SLIPPAGE = 0.00025, 0.0005, 0.001
START = pd.Timestamp('2023-09-08')
TOP_N_PER_IND = 3
MIN_AMT = 0.3e8


def _load_all(codes):
    loader = DataLoader()
    out = {}
    for c in codes:
        df = loader.load_cache(c)
        if df is None or len(df) < 100:
            continue
        df = df.copy(); df['date'] = pd.to_datetime(df['date'])
        out[c] = df.set_index('date')[['close', 'amount']]
    return out


def _year_pool(data, ind_map, asof):
    rows = []
    for c, d in data.items():
        past = d[d.index < asof].tail(250)
        if len(past) < 60 or c not in ind_map or not ind_map[c]:
            continue
        rows.append({'code': c, 'ind': ind_map[c], 'amt': float(past['amount'].mean())})
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return {}
    df = df[df['amt'] >= MIN_AMT]
    df['rank'] = df.groupby('ind')['amt'].rank(ascending=False, method='first')
    return {c: ind_map[c] for c in df[df['rank'] <= TOP_N_PER_IND]['code']}


def replay(save_json_path=None):
    full = pd.read_csv(os.path.join(DATA_DIR, 'stock_pool.csv'), dtype={'code': str})
    full['code'] = full['code'].str.zfill(6)
    codes = full['code'].tolist()
    data = _load_all(codes)

    loader = DataLoader()
    ind = loader.get_industry()[['code_std', 'industry']].rename(columns={'code_std': 'code'})
    ind['code'] = ind['code'].astype(str).str.zfill(6)
    ind_map = dict(zip(ind['code'], ind['industry']))

    idx = loader.get_index_data('000001', days=1300)
    idx['date'] = pd.to_datetime(idx['date'])
    env_map, _ = MarketEnvironment().classify_series(idx, load_sentiment())
    # 滞后确认(守则:主线需持续3天): 消除环境短脉冲的高频翻转成本
    confirmed = hysteresis_confirm(env_map, enter_n=3, exit_n=2)
    # 布尔确认态映射回环境标签(进入=持有环境; 未确认按B散乱处理)
    envs = confirmed.shift(1).ffill().map({True: 'A', False: 'B'})

    all_dates = sorted(set().union(*[set(d.index) for d in data.values()]))
    all_dates = [d for d in all_dates if d >= START]

    # 逐年池
    year_pools = {}
    for y in sorted(set(d.year for d in all_dates)):
        year_pools[y] = _year_pool(data, ind_map, pd.Timestamp(f'{y}-01-01'))

    cash, holdings = 1.0, {}
    trades, equity = [], []
    last_targets = None

    def px_of(code, day):
        d = data.get(code)
        if d is None or day not in d.index:
            return None
        v = d.loc[day, 'close']
        return float(v) if pd.notna(v) else None

    for day in all_dates:
        env = envs.get(day)
        pool = year_pools.get(day.year, {})
        targets = set(pool) if env == 'A' else set()

        # 池/环境变化 → 调仓(卖出不在目标的, 买入新目标的, 等权)
        if targets != last_targets:
            total = cash + sum(h['sh'] * (px_of(c, day) or h['last_px']) for c, h in holdings.items())
            # 卖出
            for c in list(holdings):
                if c in targets:
                    continue
                px = px_of(c, day)
                if px is None:
                    continue
                proceeds = holdings[c]['sh'] * px
                fee = proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE)
                pnl_pct = (px / holdings[c]['cost'] - 1) * 100
                cash += proceeds - fee
                trades.append({
                    'code': c, 'name': holdings[c]['name'], 'industry': holdings[c]['industry'],
                    'entry_date': holdings[c]['entry_date'], 'exit_date': str(day.date()),
                    'entry_px': round(holdings[c]['cost'], 2), 'exit_px': round(px, 2),
                    'pnl_pct': round(pnl_pct, 2), 'reason': '环境/池变动',
                })
                del holdings[c]
            # 买入/再平衡
            if targets:
                tgt = total / len(targets)
                for c in sorted(targets):
                    px = px_of(c, day)
                    if px is None or px <= 0:
                        continue
                    cur = holdings.get(c, {}).get('sh', 0.0)
                    delta = tgt - cur * px
                    if delta <= 0:
                        continue
                    afford = min(delta, max(cash, 0))
                    if afford > 0:
                        sh = afford / px / (1 + COMMISSION + SLIPPAGE)
                        cash -= sh * px * (1 + COMMISSION + SLIPPAGE)
                        if c in holdings:
                            h = holdings[c]
                            h['cost'] = (h['cost'] * h['sh'] + px * sh) / (h['sh'] + sh)
                            h['sh'] += sh
                        else:
                            holdings[c] = {'sh': sh, 'cost': px, 'entry_date': str(day.date()),
                                           'name': '', 'industry': ind_map.get(c, '')}
                        n_trades_added = True
            last_targets = targets

        # 补充名称
        for c, h in holdings.items():
            if not h['name']:
                h['name'] = h.get('_name', '')
        # 盯市
        total = cash
        for c, h in holdings.items():
            px = px_of(c, day)
            if px is not None:
                h['last_px'] = px
                total += h['sh'] * px
        equity.append({'date': day, 'equity': total})

    eq = pd.DataFrame(equity).set_index('date')['equity']

    # 持仓快照(补名称/行业)
    holdings_out = []
    total_val = float(eq.iloc[-1])
    for c, h in holdings.items():
        px = h.get('last_px') or h['cost']
        pnl = (px / h['cost'] - 1) * 100
        holdings_out.append({
            'code': c, 'name': h['name'], 'industry': h['industry'],
            'entry_date': h['entry_date'], 'entry_px': round(h['cost'], 2),
            'last_px': round(px, 2), 'pnl_pct': round(pnl, 2),
            'weight_pct': round(h['sh'] * px / total_val * 100, 1),
        })
    holdings_out.sort(key=lambda x: -x['weight_pct'])

    # 名称补全
    name_map = {}
    try:
        ind_t = DataLoader().get_industry()[['code_std', 'code_name']]
        name_map = dict(zip(ind_t['code_std'].astype(str).str.zfill(6), ind_t['code_name']))
    except Exception:
        pass
    for h in holdings_out:
        h['name'] = name_map.get(h['code'], h['name'])
    for t in trades:
        t['name'] = name_map.get(t['code'], t['name'])

    result = {
        'as_of': str(eq.index[-1].date()),
        'total_ret_pct': round((total_val - 1) * 100, 1),
        'max_dd_pct': round(((eq / eq.cummax()) - 1).min() * 100, 1),
        'n_holdings': len(holdings_out),
        'n_trades': len(trades),
        'holdings': holdings_out,
        'trades': trades[::-1][:100],   # 最近的在前, 最多100条
        'equity_dates': [str(d.date()) for d in eq.index],
        'equity_values': [round(v, 4) for v in eq.values],
    }
    if save_json_path:
        import json
        with open(save_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, allow_nan=False, default=str)
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    out = os.path.join(DATA_DIR, 'portfolio.json')
    r = replay(save_json_path=out)
    print(f"模拟持仓回放完成: 截至{r['as_of']} | 全期{r['total_ret_pct']:+.1f}% "
          f"回撤{r['max_dd_pct']}% | 持仓{r['n_holdings']}只 交易{r['n_trades']}笔")
    print(f"[OK] → {out}")
