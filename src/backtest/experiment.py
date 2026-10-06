# -*- coding: utf-8 -*-
"""
实验跑批 —— 用向量化后的快回测(约26秒/次)回答参数景观问题
==========================================================
贝叶斯纪律(见 README):
- 每个配置跑全部 walk-forward 段, 一起报告, 不挑段不挑变体
- 明确标注费用口径; 网格结果用于理解景观, 不是选优器(同样本调参=过拟合)

用法:
  python -m src.backtest.experiment --preset diagnose   # 成本诊断: 信号问题还是成本问题
  python -m src.backtest.experiment --preset weights    # 权重扰动 × 3段 walk-forward
  python -m src.backtest.experiment --preset diagnose --top 400  # 减小股票池加速
"""
import argparse
import copy
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import TRADE_CONFIG, DATA_DIR
from main import load_backtest_data
from src.strategy.multi_factor import MultiFactorStrategy

WARMUP = 120


# ---------- 配置空间 ----------

def cfg_costs(commission=0.00025, stamp=0.0005, slippage=0.001):
    """费用口径覆盖(基于完整 TRADE_CONFIG 合并, 引擎需要全部键)"""
    cfg = dict(TRADE_CONFIG)
    cfg.update({'commission_rate': commission, 'stamp_tax': stamp, 'slippage': slippage})
    return cfg


PRESET_CONFIGS = {
    # 成本诊断: -2.15% 里有多少是交易摩擦?
    'diagnose': [
        ('现行费用', None, None),
        ('仅佣金(无印花税/滑点)', None, cfg_costs(stamp=0, slippage=0)),
        ('零费用(纯信号)', None, cfg_costs(0, 0, 0)),
    ],
    # 权重扰动: BULL动量权重缩放, 看景观是否平坦(平坦=稳健, 尖峰=过拟合)
    'weights': [
        ('BULL动量x0(关闭)', {'BULL': {'momentum_20': 0.0}}, None),
        ('BULL动量x0.5', {'BULL': {'momentum_20': 0.125}}, None),
        ('基准', None, None),
        ('BULL动量x1.5', {'BULL': {'momentum_20': 0.375}}, None),
    ],
}


# ---------- 段切分与统计 ----------

def default_segments(index_df, n_segments=3):
    """从预热期后切 n 段连续窗口"""
    dates = sorted(pd.to_datetime(index_df['date'].unique()))
    trade = dates[WARMUP:]
    if len(trade) < n_segments * 10:
        return []
    bounds = np.array_split(trade, n_segments)
    return [(str(seg[0])[:10], str(seg[-1])[:10]) for seg in bounds]


def segment_stats(result, s='', e=''):
    eq = result['equity_curve'].copy()
    eq['date'] = eq['date'].astype(str)
    seg = eq
    if s:
        seg = seg[seg['date'] >= s]
    if e:
        seg = seg[seg['date'] <= e]
    if len(seg) < 2:
        return None
    ret = (seg['equity'].iloc[-1] / seg['equity'].iloc[0] - 1) * 100
    peak = seg['equity'].expanding().max()
    dd = ((seg['equity'] - peak) / peak).min() * 100
    dret = seg['equity'].pct_change().dropna()
    sharpe = dret.mean() / (dret.std() + 1e-8) * np.sqrt(252) if len(dret) > 1 else 0.0
    tr = result.get('trades')
    if tr is not None and len(tr) > 0:
        sells = tr[tr['action'] == 'SELL']
        win = (sells['pnl'] > 0).sum() / len(sells) * 100 if len(sells) else 0.0
        n_trades = int(len(tr))
    else:
        win, n_trades = 0.0, 0
    return {'ret_pct': round(ret, 2), 'max_dd_pct': round(dd, 2),
            'sharpe': round(sharpe, 2), 'win_rate': round(win, 1), 'n_trades': n_trades}


# ---------- 执行 ----------

def run_sweep(data_dict, index_df, pool, configs, segments, verbose=True):
    """
    configs: [(label, regime_override|None, engine_cfg|None), ...]
    segments: [(start, end), ...]; 空列表 = 单段(全期)
    返回: DataFrame[label, seg, start, end, ret_pct, max_dd_pct, sharpe, win_rate, n_trades]
    """
    segs = segments or [(None, None)]
    rows = []
    strategy = MultiFactorStrategy()
    for label, override, engine_cfg in configs:
        for k, (s, e) in enumerate(segs):
            tag = f"seg{k+1}" if segments else "full"
            if verbose:
                print(f"\n>>> {label} | {tag} {s or ''}~{e or ''}", flush=True)
            result = strategy.backtest_with_regime(
                data_dict, index_df, pool,
                start_date=s, end_date=e,
                engine_cfg=copy.deepcopy(engine_cfg),
                regime_override=copy.deepcopy(override),
            )
            if result is None:
                rows.append({'label': label, 'seg': tag, 'start': s, 'end': e,
                             'ret_pct': np.nan, 'max_dd_pct': np.nan,
                             'sharpe': np.nan, 'win_rate': np.nan, 'n_trades': 0})
                continue
            # 统一走 segment_stats(空起止=全期), 保证各口径统计完整一致
            st = segment_stats(result, s or '', e or '')
            if st is None:
                st = {'ret_pct': np.nan, 'max_dd_pct': np.nan, 'sharpe': np.nan,
                      'win_rate': np.nan, 'n_trades': 0}
            rows.append({'label': label, 'seg': tag, 'start': s, 'end': e, **st})

    df = pd.DataFrame(rows)
    if verbose:
        cols = ['label', 'seg', 'ret_pct', 'max_dd_pct', 'sharpe', 'win_rate', 'n_trades']
        print('\n' + '=' * 70)
        print(df[cols].to_string(index=False))
        if segments and len(df):
            piv = df.pivot_table(index='label', columns='seg', values='ret_pct', aggfunc='first')
            piv['平均'] = piv.mean(axis=1).round(2)
            print('\n分段收益透视(全部段一起看, 防单段运气):')
            print(piv.round(2).to_string())
    return df


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--preset', choices=['diagnose', 'weights'], default='diagnose')
    ap.add_argument('--top', type=int, default=800, help='股票池前N只')
    ap.add_argument('--segments', type=int, default=3)
    ap.add_argument('--save', action='store_true', help='结果存 data/experiments/')
    args = ap.parse_args()

    print(f'加载回测数据(前{args.top}只)...')
    pool, data_dict, index_df = load_backtest_data(top_n=args.top)
    if data_dict is None or len(data_dict) < 5:
        print('[!] 数据不足')
        return

    configs = PRESET_CONFIGS[args.preset]
    segments = default_segments(index_df, args.segments) if args.preset == 'weights' else []

    df = run_sweep(data_dict, index_df, pool, configs, segments)

    if args.save:
        out_dir = os.path.join(DATA_DIR, 'experiments')
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f'{args.preset}_{pd.Timestamp.now():%Y%m%d_%H%M}.csv')
        df.to_csv(path, index=False, encoding='utf-8-sig')
        print(f'\n[OK] 结果 → {path}')


if __name__ == '__main__':
    main()
