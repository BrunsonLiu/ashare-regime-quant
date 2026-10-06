# -*- coding: utf-8 -*-
"""
Regime 条件因子有效性 —— 回答"抓主要矛盾"是否可行
==================================================
问题: 因子有效性是否随市场状态(BULL/SHOCK/BEAR)变化?
      若变化显著 → 状态自适应有价值; 若各状态都一样 → 切换无意义。
      若状态识别滞后 → 切换来不及, 反而增加换手成本。

方法(严格无前视):
- 每日T用 data<T 判状态(实盘可得的)
- 因子值取 T-1 收盘; 前向收益 = T+1开盘 → T+1+N开盘(与回测同一时序契约)
- 横截面 Spearman IC(因子 vs 前向收益), 按状态分组统计
- 报告: 因子×状态 IC 矩阵 + 状态分布 + 状态持续天数(识别是否够早)

用法: python -m src.backtest.regime_ic --top 300 --horizon 5
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from main import load_backtest_data
from src.strategy.multi_factor import MultiFactorStrategy

HORIZON = 5
MA_SHORT, MA_LONG = 20, 60


def regime_series(index_df, ma_short=MA_SHORT, ma_long=MA_LONG):
    """逐日状态(用 data<=该日, 与 MarketRegime.detect 的判定口径一致但简化:
    这里只用均线+波动, 因为要覆盖全部交易日且避免慢牛120日窗口前段缺失)"""
    idx = index_df.sort_values('date').reset_index(drop=True)
    close = idx['close']
    ma_s = close.rolling(ma_short).mean()
    ma_l = close.rolling(ma_long).mean()
    vol = close.pct_change().rolling(20).std()
    regime = []
    for i in range(len(idx)):
        if i < ma_long or pd.isna(ma_s.iloc[i]) or pd.isna(ma_l.iloc[i]):
            regime.append('WARMUP')
        elif ma_s.iloc[i] > ma_l.iloc[i] * 1.02:
            regime.append('BULL')
        elif ma_s.iloc[i] < ma_l.iloc[i] * 0.98:
            regime.append('BEAR')
        else:
            regime.append('SHOCK')
    return dict(zip(pd.to_datetime(idx['date']), regime))


def forward_returns(data_dict, horizon):
    """{code: {Timestamp: T+1开盘→T+1+horizon开盘 的收益}}
    键统一用 pd.Timestamp(与 regime_series 一致), 避免 numpy datetime64 与
    Timestamp 哈希不一致导致的查不到"""
    out = {}
    for code, df in data_dict.items():
        d = df.sort_values('date').reset_index(drop=True)
        dates = pd.to_datetime(d['date'])          # Series → 元素为 Timestamp
        opens = d['open'].values.astype(float)
        n = len(d)
        m = {}
        for i in range(n):
            j = i + 1 + horizon
            if i + 1 >= n or j >= n:
                continue
            m[dates.iloc[i]] = opens[j] / opens[i + 1] - 1
        out[code] = m
    return out


def daily_ic(panels, fwd, reg_map, factor_names, horizon):
    """
    逐日横截面 IC: 因子(T-1值) vs 前向收益
    返回 rows: [{date, regime, factor, ic, n}]
    """
    rows = []
    # 用因子面板取 T-1 行: searchsorted
    codes = list(panels.keys())
    # 统一日期轴
    all_dates = sorted(set().union(*[set(fwd[c].keys()) for c in codes if fwd.get(c)]))
    # 预取每只股票每因子的 T-1 值
    for T in all_dates:
        reg = reg_map.get(pd.Timestamp(T), 'WARMUP')
        if reg == 'WARMUP':
            continue
        recs = {}
        for code in codes:
            fr = fwd.get(code, {}).get(T)
            if fr is None:
                continue
            p = panels[code]
            pos = np.searchsorted(p['dates'], np.datetime64(T), side='left') - 1
            if pos < 60:
                continue
            rec = {'code': code, 'fwd': fr}
            for fn in factor_names:
                arr = p['factors'].get(fn)
                if arr is not None:
                    rec[fn] = arr[pos]
            recs[code] = rec
        if len(recs) < 30:
            continue
        df = pd.DataFrame(list(recs.values()))
        for fn in factor_names:
            if fn not in df.columns:
                continue
            sub = df[[fn, 'fwd']].dropna()
            if len(sub) < 30 or sub[fn].nunique() < 3:
                continue
            ic = sub[fn].rank().corr(sub['fwd'].rank())  # Spearman
            rows.append({'date': T, 'regime': reg, 'factor': fn, 'ic': ic, 'n': len(sub)})
    return pd.DataFrame(rows)


def regime_persistence(reg_map):
    """状态持续天数(识别是否够早: 切换后平均持续多少天)"""
    ser = [v for _, v in sorted(reg_map.items()) if v != 'WARMUP']
    if not ser:
        return {}
    runs = {}
    cur, cnt = ser[0], 1
    for v in ser[1:]:
        if v == cur:
            cnt += 1
        else:
            runs.setdefault(cur, []).append(cnt)
            cur, cnt = v, 1
    runs.setdefault(cur, []).append(cnt)
    return {k: {'段数': len(v), '平均天数': round(np.mean(v), 1), '中位天': int(np.median(v)), '最长': max(v)}
            for k, v in runs.items()}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=300)
    ap.add_argument('--index-days', type=int, default=400, help='回测时间轴长度(日历天), 多周期传1300')
    ap.add_argument('--horizon', type=int, default=HORIZON)
    ap.add_argument('--save', action='store_true')
    args = ap.parse_args()

    pool, data_dict, index_df = load_backtest_data(top_n=args.top, index_days=args.index_days)
    if data_dict is None or len(data_dict) < 30:
        print('[!] 数据不足'); return

    strategy = MultiFactorStrategy()
    factor_names = sorted(set().union(*[set(strategy.regime.get_factor_weights(r).keys())
                                        for r in ('BULL', 'BEAR', 'SHOCK')]))
    factor_names = [f for f in factor_names if f in strategy.engine.factors]

    print(f'universe={len(data_dict)} 因子={len(factor_names)} 前向期={args.horizon}日')
    reg_map = regime_series(index_df)

    from collections import Counter
    dist = Counter(v for v in reg_map.values() if v != 'WARMUP')
    total = sum(dist.values())
    print('状态分布:', {k: f'{v}天({v/total*100:.0f}%)' for k, v in dist.most_common()})
    pers = regime_persistence(reg_map)
    print('状态持续:', pers)

    print('\n预计算因子面板...')
    panels = strategy.precompute_factor_panels(data_dict)
    fwd = forward_returns(data_dict, args.horizon)
    print('逐日横截面 IC...')
    ic = daily_ic(panels, fwd, reg_map, factor_names, args.horizon)

    if len(ic) == 0:
        print('[!] 无有效IC'); return

    mat = ic.pivot_table(index='factor', columns='regime', values='ic', aggfunc='mean')
    cnt = ic.pivot_table(index='factor', columns='regime', values='ic', aggfunc='count')
    order = [c for c in ['BULL', 'SHOCK', 'BEAR'] if c in mat.columns]
    mat = mat[order]
    print('\n=== 因子 × 状态 平均IC ===')
    print('(IC>0.03 视为有预测力; |IC|<0.02 视为噪声; 看同一因子在不同状态的IC差异)')
    print(mat.round(4).to_string())
    print('\n各状态有效样本天数:', {c: int(cnt[c].dropna().iloc[0]) if c in cnt else 0 for c in order})

    # 关键: 每个因子跨状态的IC极差(越大=越需要切换)
    mat['状态间极差'] = (mat.max(axis=1) - mat.min(axis=1)).round(4)
    print('\n跨状态IC极差(大=该因子强烈依赖状态, 值得切换):')
    print(mat['状态间极差'].sort_values(ascending=False).round(4).to_string())

    if args.save:
        out_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), 'data', 'experiments')
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f'regime_ic_{pd.Timestamp.now():%Y%m%d_%H%M}.csv')
        ic.to_csv(path, index=False, encoding='utf-8-sig')
        print(f'\n[OK] 逐日IC → {path}')


if __name__ == '__main__':
    main()
