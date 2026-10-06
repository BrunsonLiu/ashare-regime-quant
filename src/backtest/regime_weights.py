# -*- coding: utf-8 -*-
"""
Regime IC 权重策略 —— 检验"状态自适应"能否带来真样本外超额
==========================================================
主线假设(来自 regime_ic 分析): 因子有效性随状态翻转, 若能按状态配权,
应优于固定权重。

严格防过拟合:
- 权重只从**训练段** IC 估计(每个状态内: 因子IC → 归一化权重, |IC|过小则剔除)
- 在**测试段**(训练段之后)回测, 绝不回看
- 全段/多段一起报告(贝叶斯纪律), 与固定权重基准对照

用法:
  python -m src.backtest.regime_weights --top 300 --train-end 2026-05-31
"""
import argparse
import copy
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from main import load_backtest_data
from src.strategy.multi_factor import MultiFactorStrategy
from src.backtest.experiment import run_sweep
from src.backtest.regime_ic import regime_series, forward_returns

IC_MIN = 0.015   # |IC|低于此视为噪声, 不参与权重
HORIZON = 5


def compute_ic_weights(panels, fwd, reg_map, factor_names, train_dates):
    """
    从训练段逐日IC估计各状态下的权重: weight ∝ mean(IC | state), 归一化(|w|和为1)
    返回 {regime: {factor: weight}}
    """
    # 训练段逐日横截面 IC
    ic_rows = []
    codes = list(panels.keys())
    for T in train_dates:
        reg = reg_map.get(pd.Timestamp(T), 'WARMUP')
        if reg == 'WARMUP':
            continue
        recs = []
        for code in codes:
            fr = fwd.get(code, {}).get(pd.Timestamp(T))
            if fr is None:
                continue
            p = panels[code]
            pos = np.searchsorted(p['dates'], np.datetime64(T), side='left') - 1
            if pos < 60:
                continue
            rec = {'fwd': fr}
            for fn in factor_names:
                arr = p['factors'].get(fn)
                if arr is not None:
                    rec[fn] = arr[pos]
            recs.append(rec)
        if len(recs) < 30:
            continue
        df = pd.DataFrame(recs)
        for fn in factor_names:
            if fn not in df.columns:
                continue
            sub = df[[fn, 'fwd']].dropna()
            if len(sub) < 30 or sub[fn].nunique() < 3:
                continue
            ic_rows.append({'date': T, 'regime': reg, 'factor': fn,
                            'ic': sub[fn].rank().corr(sub['fwd'].rank())})
    ic = pd.DataFrame(ic_rows)
    if len(ic) == 0:
        return {}, {}

    mat = ic.pivot_table(index='factor', columns='regime', values='ic', aggfunc='mean')
    n_by_regime = ic.groupby('regime')['date'].nunique().to_dict()

    weights = {}
    for regime in ('BULL', 'SHOCK', 'BEAR'):
        if regime not in mat.columns:
            weights[regime] = {}
            continue
        col = mat[regime].dropna()
        col = col[col.abs() >= IC_MIN]
        if len(col) == 0 or col.abs().sum() == 0:
            weights[regime] = {}
            continue
        # 归一化: |w| 之和为 1(保留符号)
        w = col / col.abs().sum()
        weights[regime] = {k: round(float(v), 4) for k, v in w.items()}
    return weights, {'ic_matrix': mat, 'days_by_regime': n_by_regime}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=300)
    ap.add_argument('--index-days', type=int, default=400, help='回测时间轴长度(日历天), 多周期传1300')
    ap.add_argument('--train-end', default='2026-05-31', help='训练段截止(之后为测试段)')
    ap.add_argument('--save', action='store_true')
    args = ap.parse_args()

    pool, data_dict, index_df = load_backtest_data(top_n=args.top, index_days=args.index_days)
    if data_dict is None or len(data_dict) < 30:
        print('[!] 数据不足'); return

    strategy = MultiFactorStrategy()
    factor_names = sorted(set().union(*[set(strategy.regime.get_factor_weights(r).keys())
                                        for r in ('BULL', 'BEAR', 'SHOCK')]))
    factor_names = [f for f in factor_names if f in strategy.engine.factors]

    reg_map = regime_series(index_df)
    panels = strategy.precompute_factor_panels(data_dict)
    fwd = forward_returns(data_dict, HORIZON)

    all_dates = sorted(pd.to_datetime(index_df['date'].unique()))
    train_end = pd.Timestamp(args.train_end)
    train_dates = [d for d in all_dates if d <= train_end]
    test_dates = [d for d in all_dates if d > train_end]
    print(f'universe={len(data_dict)} 训练<= {args.train_end}({len(train_dates)}日) '
          f'测试> {args.train_end}({len(test_dates)}日)')

    weights, meta = compute_ic_weights(panels, fwd, reg_map, factor_names, train_dates)
    print('\n=== 训练段估计的状态权重 (|IC|>=%.3f, 归一化) ===' % IC_MIN)
    for r in ('BULL', 'SHOCK', 'BEAR'):
        ws = weights.get(r, {})
        print(f'  {r} (训练IC日={meta.get("days_by_regime", {}).get(r, 0)}): '
              + (', '.join(f'{k}:{v:+.3f}' for k, v in sorted(ws.items(), key=lambda x: -abs(x[1])))
                 if ws else '(无可用因子)'))

    if not weights.get('SHOCK') and not weights.get('BEAR'):
        print('[!] 训练段未估计出有效权重, 退出'); return

    # 测试段: IC权重 vs 固定权重基准
    test_segments = []
    test_start = str(test_dates[0])[:10] if test_dates else None
    configs = [
        ('IC权重(状态自适应)', {'_replace': None, **{r: {f: w for f, w in weights.get(r, {}).items()}
                                                   for r in ('BULL', 'SHOCK', 'BEAR')}}, None),
        ('固定权重基准', None, None),
    ]
    # 修正: _replace 若存在则整表替换, 这里用按状态覆盖(保留基础表的其他因子则不适用)
    # 用纯覆盖: _replace 置为"各状态的完全替换表" —— 通过特殊处理
    configs = [
        ('IC权重(状态自适应)', {'_regime_tables': weights}, None),
        ('固定权重基准', None, None),
    ]

    df = run_sweep(data_dict, index_df, pool, configs,
                   [(test_start, None)] if test_start else [], verbose=True)

    if args.save and len(df):
        out_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), 'data', 'experiments')
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f'regime_weights_{pd.Timestamp.now():%Y%m%d_%H%M}.csv')
        df.to_csv(path, index=False, encoding='utf-8-sig')
        print(f'\n[OK] → {path}')


if __name__ == '__main__':
    main()
