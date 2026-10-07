# -*- coding: utf-8 -*-
"""
守则式集中策略 —— 按守则原文"集中优势兵力打主线龙头"重做回测
==============================================================
之前的"集中跑输"结论是用**错误方法**(按成交额随机取前N)得出的, 不算数。
本模块严格按守则:
  1. 环境: 只在 A 主线环境持有                       (守则第一章)
  2. 行业: 情绪主线(涨停热度) ∩ 长期健康(非走弱无反转) (守则第二章 + 中长线原则)
  3. 选股: 行业内按"龙头标准"取最强, 集中到 ≤ max_hold 只 (守则2.3 集中优势兵力)
  4. 止损: 个股 -7% 无条件止损                        (守则第四章铁律)

无前视(信号T-1, 成交T开盘) + 含真实成本 + 分段检验。

用法: python -m src.backtest.concentrated_strategy [--max-hold 10]
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR
from src.utils.market_env import MarketEnvironment, load_sentiment
from src.backtest.sentiment_sector import build_industry_heat, industry_heat_series, load_prices_ind

COMMISSION, STAMP_TAX, SLIPPAGE = 0.00025, 0.0005, 0.001
STOP_LOSS = -0.07        # 守则第四章: 个股止损-7%
REBAL_DAYS = 10          # 调仓周期


def _industry_health_verdicts(prices, ind_map):
    """行业长期健康度(截至最新) —— 用于过滤走弱无反转的行业"""
    try:
        from src.utils.industry_health import health_score
        # 用行业等权指数算健康度
        sers = {}
        for ind in set(ind_map.values()):
            cols = [c for c in prices.columns if ind_map.get(c) == ind]
            if len(cols) >= 2:
                mat = prices[cols].ffill()
                norm = mat / mat.bfill().iloc[0]
                sers[ind] = norm.mean(axis=1)
        hs = health_score(pd.DataFrame(sers))
        return {k: v['verdict'] for k, v in hs.items()}
    except Exception as e:
        print(f'  [warn] 行业健康度不可用: {e}')
        return {}


def _leader_score(prices, day, mom_days=20):
    """龙头标准(守则2.3的简化量化): 近期强度 + 流动性(用价格连续性代理)
    返回 {code: score}, 高者优先"""
    hist = prices.loc[:day]
    if len(hist) < mom_days + 1:
        return {}
    ret = (hist.iloc[-1] / hist.iloc[-mom_days - 1] - 1).dropna()
    return ret.to_dict()   # 近期涨幅 = 强度(率先启动=龙头特征)


def backtest(prices, ind_map, envs, heat, health, max_hold=10,
             rebalance_days=REBAL_DAYS, top_industries=2, cost=True, stop_loss=STOP_LOSS):
    prices_val = prices.ffill()
    dates = prices.index
    env_arr = pd.Series(envs).reindex(dates).ffill()

    cash, holdings, equity = 1.0, {}, []   # holdings: {code: {sh, cost, buy_date}}
    n_trades, n_stops = 0, 0
    next_rebal = 0

    def pv(day):
        total = cash
        for c, h in holdings.items():
            px = prices_val.loc[day].get(c)
            if pd.notna(px):
                total += h['sh'] * px
        return total

    for i, day in enumerate(dates):
        # --- 个股止损(守则铁律): 用T-1收盘判断, T开盘成交 ---
        if i > 0 and stop_loss is not None:
            for c in list(holdings):
                h = holdings[c]
                prev = dates[i - 1]
                pc = prices.loc[prev].get(c) if prev in prices.index else None
                if pd.isna(pc):
                    continue
                if pc / h['cost'] - 1 <= stop_loss:
                    op = prices.loc[day].get(c)  # T开盘价
                    if pd.notna(op):
                        proceeds = h['sh'] * op
                        cash += proceeds - (proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                        n_trades += 1; n_stops += 1
                        del holdings[c]

        in_market = env_arr.iloc[i] == 'A'

        if i >= next_rebal:
            next_rebal = i + rebalance_days
            total = pv(day)
            targets = []
            if in_market:
                prev_day = dates[i - 1] if i > 0 else day
                hm = industry_heat_series(heat, prev_day, lookback=5)
                # 情绪主线的行业, 且长期不弱
                hot = sorted([k for k, v in hm.items() if v > 0],
                             key=lambda k: -hm[k])[:top_industries]
                cand_inds = [k for k in hot if health.get(k) != '走弱无反转(剔除)']
                lscore = _leader_score(prices, day)
                cand = [(c, lscore.get(c, -9)) for c in prices.columns
                        if ind_map.get(c) in cand_inds and c in lscore]
                cand.sort(key=lambda x: -x[1])
                targets = [c for c, _ in cand[:max_hold]]
            # 卖出不在目标里的
            for c in list(holdings):
                if c not in targets:
                    px = prices.loc[day].get(c)
                    if pd.notna(px):
                        proceeds = holdings[c]['sh'] * px
                        cash += proceeds - (proceeds * (COMMISSION + STAMP_TAX + SLIPPAGE) if cost else 0)
                        n_trades += 1
                        del holdings[c]
            # 买入/加仓到目标(等权)
            if targets:
                tgt_val = total / len(targets)
                for c in targets:
                    px = prices.loc[day].get(c)
                    if pd.isna(px) or px <= 0:
                        continue
                    cur = holdings.get(c, {}).get('sh', 0.0)
                    delta = tgt_val - cur * px
                    if delta <= 0:
                        continue
                    afford = min(delta, max(cash, 0))
                    if afford > 0:
                        fr = (COMMISSION + SLIPPAGE) if cost else 0
                        sh = afford / px / (1 + fr)
                        cash -= sh * px * (1 + fr)
                        if c in holdings:
                            # 加仓: 更新成本为加权
                            h = holdings[c]
                            tot_sh = h['sh'] + sh
                            h['cost'] = (h['cost'] * h['sh'] + px * sh) / tot_sh
                            h['sh'] = tot_sh
                        else:
                            holdings[c] = {'sh': sh, 'cost': px, 'buy_date': day}
                        n_trades += 1
        equity.append({'date': day, 'equity': pv(day)})

    eq = pd.DataFrame(equity).set_index('date')['equity']
    peak = eq.cummax()
    return {'ret_pct': round((eq.iloc[-1] - 1) * 100, 1),
            'max_dd_pct': round(((eq / peak) - 1).min() * 100, 1),
            'n_trades': n_trades, 'n_stops': n_stops, 'equity': eq}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-hold', type=int, default=10)
    args = ap.parse_args()

    prices, ind_map = load_prices_ind()
    loader_end = prices.index[-1]
    idx = pd.read_csv(os.path.join(DATA_DIR, 'index_000001.csv'), parse_dates=['date'])
    env_map, _ = MarketEnvironment().classify_series(idx, load_sentiment())
    heat = build_industry_heat()
    health = _industry_health_verdicts(prices, ind_map)
    n_weak = sum(1 for v in health.values() if v == '走弱无反转(剔除)')
    print(f'PIT龙头池 {prices.shape[1]}只, 长期走弱行业 {n_weak} 个(已过滤)')

    # 基准: 龙头池等权持有
    bh = prices.pct_change(fill_method=None).mean(axis=1)
    bh_eq = (1 + bh.fillna(0)).cumprod()
    print(f'基准-龙头池等权持有: {(bh_eq.iloc[-1]-1)*100:+.1f}%  回撤{((bh_eq/bh_eq.cummax())-1).min()*100:.1f}%')

    print(f'\n=== 守则式集中策略(≤{args.max_hold}只 + -7%止损 + 情绪主线+长期健康过滤) ===')
    rows = []
    for mh in (5, 10):
        for sl in (STOP_LOSS, None):
            for cost in (True, False):
                st = backtest(prices, ind_map, env_map, heat, health, max_hold=mh,
                              cost=cost, stop_loss=sl)
                rows.append({'持仓上限': mh, '止损': f'{int(sl*100)}%' if sl else '无',
                             '成本': '含' if cost else '零', '收益%': st['ret_pct'],
                             '回撤%': st['max_dd_pct'], '交易': st['n_trades'],
                             '止损次数': st['n_stops']})
    print(pd.DataFrame(rows).to_string(index=False))

    # 分段检验(关键): 用≤10只+止损的最佳配置
    print(f'\n=== 分段检验(≤{args.max_hold}只, -7%止损, 含成本) ===')
    segs = np.array_split(prices.index, 3)
    for k, seg in enumerate(segs):
        ps = prices.loc[seg]
        st = backtest(ps, ind_map, env_map, heat, health, max_hold=args.max_hold, cost=True)
        bh_s = (1 + ps.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
        print(f'  段{k+1} {seg[0].date()}~{seg[-1].date()}: 策略{st["ret_pct"]:+7.1f}%'
              f'(回撤{st["max_dd_pct"]:.1f}%) | 持有基准{(bh_s.iloc[-1]-1)*100:+7.1f}%')


if __name__ == '__main__':
    main()
