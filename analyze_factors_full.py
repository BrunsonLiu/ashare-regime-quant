# -*- coding: utf-8 -*-
"""
全量因子 IC/IR 分析
逐个日期计算所有因子的横截面 IC，汇总每个因子的有效性评估
输出到 data/factor_icir.csv 和 data/factor_quantile.csv

用法:
  python analyze_factors_full.py                          # 默认: PIT龙头池, 3.5年
  python analyze_factors_full.py --pool stock_pool.csv    # 全池
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from config import DATA_DIR
from src.strategy.multi_factor import MultiFactorStrategy
from main import load_backtest_data

# ============ 配置 ============
PERIODS = [1, 5, 10, 20]
MIN_HISTORY = 60    # 因子计算最少历史天数
OUT_ICIR = os.path.join(DATA_DIR, 'factor_icir.csv')
OUT_QUANTILE = os.path.join(DATA_DIR, 'factor_quantile.csv')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--pool', default='stock_pool_leaders_pit.csv',
                    help='股票池文件(默认PIT龙头池)')
    ap.add_argument('--top', type=int, default=300)
    ap.add_argument('--index-days', type=int, default=1300,
                    help='时间轴长度(日历天), 多周期传1300')
    ap.add_argument('--samples', type=int, default=40, help='抽样日期数')
    args = ap.parse_args()

    print("=" * 60)
    print(f"全量因子 IC/IR 分析 ({args.pool})")
    print("=" * 60)

    pool, data_dict, index_df = load_backtest_data(
        top_n=args.top, index_days=args.index_days, pool_file=args.pool,
        board_filter=False)
    if data_dict is None or len(data_dict) < 30:
        print("数据不足, 请先拉取长历史: python scripts/fetch_long_history.py")
        return
    print(f"universe: {len(data_dict)} 只")

    # ============ 初始化策略（注册所有因子） ============
    print("初始化因子引擎...")
    strategy = MultiFactorStrategy()
    engine = strategy.engine
    factor_names = list(engine.factors.keys())
    print(f"已注册 {len(factor_names)} 个因子")

    # ============ 因子面板(向量化) + 抽样日期 ============
    print("预计算因子面板...")
    panels = strategy.precompute_factor_panels(data_dict)

    all_dates = sorted(set().union(*[set(pd.to_datetime(d['date']).values)
                                     for d in data_dict.values()]))
    # 只取各股均有足够历史的时段起点之后
    start_date = all_dates[MIN_HISTORY] if len(all_dates) > MIN_HISTORY else all_dates[0]
    trade_dates = [d for d in all_dates if d >= start_date]
    step = max(1, len(trade_dates) // args.samples)
    trade_dates = trade_dates[::step]
    print(f"分析日期(抽样): {pd.Timestamp(trade_dates[0]).date()} ~ "
          f"{pd.Timestamp(trade_dates[-1]).date()} ({len(trade_dates)}天)")

    # ============ 横截面因子值(面板行查找, 语义=旧版"≤date取末行") ============
    print("计算横截面因子值...")
    lookup = {}
    for code, panel in panels.items():
        pos = np.searchsorted(panel['dates'], np.asarray(trade_dates, dtype='datetime64[ns]'),
                              side='right') - 1   # 最后一行 ≤ T (与旧版 df_u = data ≤ date 一致)
        valid = pos >= MIN_HISTORY - 1
        lookup[code] = {'row': np.where(valid, pos, -1),
                        'factors': panel['factors'],
                        'dates': panel['dates']}

    # 每只股票的收盘价数组
    closes = {code: np.asarray(d.sort_values('date')['close'], dtype=float)
              for code, d in data_dict.items()}

    factor_records = []
    return_records = []
    for di, date in enumerate(trade_dates):
        if (di + 1) % 10 == 0:
            print(f"  进度: {di+1}/{len(trade_dates)} ({pd.Timestamp(date).date()})")
        t64 = np.datetime64(pd.Timestamp(date))
        for code, lu in lookup.items():
            r = lu['row'][di]
            if r < 0:
                continue
            rec = {'date': date, 'code': code}
            all_nan = True
            for fname, arr in lu['factors'].items():
                v = arr[r]
                rec[fname] = v if pd.notna(v) else np.nan
                if pd.notna(v):
                    all_nan = False
            if all_nan:
                continue
            factor_records.append(rec)
            # close ≤ T 的最后一行(与因子同一时点)
            ci = np.searchsorted(lu['dates'], t64, side='right') - 1
            return_records.append({'date': date, 'code': code,
                                   'close': float(closes[code][ci])})

    factor_df = pd.DataFrame(factor_records)
    return_df = pd.DataFrame(return_records)
    print(f"因子数据: {factor_df.shape} (行={len(factor_df)}, 因子列={len(factor_names)})")

    # ============ IC/IR 分析 ============
    print("\n" + "=" * 60)
    print("IC/IR 分析中...")
    print("=" * 60)

    merged = return_df.merge(factor_df, on=['date', 'code'], how='inner')
    merged = merged.sort_values(['code', 'date'])
    for p in PERIODS:
        merged[f'fwd_ret_{p}'] = merged.groupby('code')['close'].pct_change(p).shift(-p)

    ic_results = []
    quantile_results = []

    valid_factors = []
    for fname in factor_names:
        if fname not in merged.columns:
            continue
        if merged[fname].notna().sum() < 100:
            continue
        valid_factors.append(fname)

    print(f"有效因子: {len(valid_factors)}/{len(factor_names)} 个")

    for fi, fname in enumerate(valid_factors):
        print(f"\n[{fi+1}/{len(valid_factors)}] {fname}...")

        for period in PERIODS:
            ret_col = f'fwd_ret_{period}'
            ic_list = []
            for date in sorted(merged['date'].unique()):
                day = merged[merged['date'] == date].dropna(subset=[fname, ret_col])
                if len(day) < 10:
                    continue
                try:
                    ic, _ = spearmanr(day[fname].astype(float), day[ret_col].astype(float))
                except Exception:
                    ic = np.nan
                if pd.notna(ic):
                    ic_list.append({'date': date, 'ic': ic})

            ic_series = [x['ic'] for x in ic_list]
            if len(ic_series) < 5:
                continue
            mean_ic = np.mean(ic_series)
            std_ic = np.std(ic_series)
            ir = mean_ic / std_ic if std_ic > 0 else 0
            win_rate = sum(1 for x in ic_series if x > 0) / len(ic_series) * 100

            if ir > 0.5 and win_rate > 55:
                verdict = '✅ 有效'
            elif ir > 0.25:
                verdict = '⚠️ 一般'
            else:
                verdict = '❌ 无效'

            ic_results.append({
                '因子': fname, '周期': f'{period}日',
                'IC均值': round(mean_ic, 4), 'IC标准差': round(std_ic, 4),
                'IR': round(ir, 4), 'IC胜率': f'{win_rate:.1f}%',
                '样本数': len(ic_series), '评估': verdict
            })

        period = 5
        ret_col = f'fwd_ret_{period}'
        valid = merged.dropna(subset=[fname, ret_col])
        if len(valid) < 50:
            continue
        groups_ret = []
        for date in sorted(valid['date'].unique()):
            day = valid[valid['date'] == date].dropna(subset=[fname, ret_col])
            if len(day) < 20:
                continue
            try:
                day['group'] = pd.qcut(day[fname].astype(float), 5, labels=False, duplicates='drop')
            except Exception:
                continue
            gr = day.groupby('group')[ret_col].mean()
            if 4 in gr.index and 0 in gr.index:
                groups_ret.append({'date': date, 'long': gr[4], 'short': gr[0],
                                   'long_short': gr[4] - gr[0]})
        if len(groups_ret) < 5:
            continue
        gr_df = pd.DataFrame(groups_ret)
        ls_mean = gr_df['long_short'].mean()
        ls_win = (gr_df['long_short'] > 0).mean() * 100
        quantile_results.append({
            '因子': fname,
            '多组平均': f"{gr_df['long'].mean()*100:.2f}%",
            '空组平均': f"{gr_df['short'].mean()*100:.2f}%",
            '多空差': f"{ls_mean*100:.2f}%",
            '多空胜率': f"{ls_win:.1f}%",
            '分组单调': '✅' if ls_mean > 0.005 and ls_win > 55 else '❌',
        })

    # ============ 汇总输出 ============
    ic_df = pd.DataFrame(ic_results)
    qt_df = pd.DataFrame(quantile_results) if quantile_results else pd.DataFrame()

    if len(ic_df) > 0:
        ic5 = ic_df[ic_df['周期'] == '5日'].sort_values('IR', ascending=False)
        print("\n" + "=" * 60)
        print("=== 因子有效性排名 (5日周期, 按IR排序) ===")
        print("=" * 60)
        print(ic5.to_string(index=False))

        print("\n" + "=" * 60)
        print("=== 各因子最佳周期汇总 ===")
        print("=" * 60)
        best_periods = ic_df.loc[ic_df.groupby('因子')['IR'].idxmax()].sort_values('IR', ascending=False)
        print(best_periods.to_string(index=False))

    ic_df.to_csv(OUT_ICIR, index=False, encoding='utf-8-sig')
    print(f"\n[OK] IC/IR 已保存: {OUT_ICIR}")

    if len(qt_df) > 0:
        qt_df.to_csv(OUT_QUANTILE, index=False, encoding='utf-8-sig')
        print(f"[OK] 分组收益已保存: {OUT_QUANTILE}")
        print("\n=== 5分组收益 (多空差) ===")
        print(qt_df.sort_values('多空差', ascending=False).to_string(index=False))

    print(f"\n[OK] 因子分析完成, 共分析 {len(valid_factors)} 个因子")


if __name__ == '__main__':
    main()
