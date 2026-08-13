# -*- coding: utf-8 -*-
"""
全量因子 IC/IR 分析
逐个日期计算所有因子的横截面 IC，汇总每个因子的有效性评估
输出到 data/factor_icir.csv 和 data/factor_quantile.csv
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import spearmanr

from config import DATA_DIR
from src.stock_pool import StockPool
from src.data_loader import DataLoader
from src.strategy.multi_factor import MultiFactorStrategy

# ============ 配置 ============
TOP_N = 100        # 用前100只（OOM限制，沙箱约2GB）
PERIODS = [1, 5, 10, 20]
MIN_HISTORY = 60    # 因子计算最少历史天数
OUT_ICIR = os.path.join(DATA_DIR, 'factor_icir.csv')
OUT_QUANTILE = os.path.join(DATA_DIR, 'factor_quantile.csv')

# ============ 加载数据 ============
print("="*60)
print("全量因子 IC/IR 分析")
print("="*60)

sp = StockPool()
pool = sp.load()
pool['code'] = pool['code'].astype(str).str.zfill(6)
pool = pool[~pool['code'].str.startswith('30') & ~pool['code'].str.startswith('68')]
if 'amount' in pool.columns:
    pool = pool.sort_values('amount', ascending=False)
codes = pool['code'].head(TOP_N).tolist()
print(f"加载 {len(codes)} 只股票...")

loader = DataLoader()
data_dict = {}
for code in codes:
    df = loader.load_cache(code)
    if df is not None and len(df) > MIN_HISTORY:
        df['date'] = pd.to_datetime(df['date'])
        data_dict[code] = df
print(f"有效: {len(data_dict)} 只")

# 取每5天一个抽样的日期（减少内存压力）
all_dates = set()
for df in data_dict.values():
    all_dates.update(df['date'].unique())
trade_dates = sorted(list(all_dates))
sample_code = list(data_dict.keys())[0]
stock_dates = sorted(data_dict[sample_code]['date'].unique())
if len(stock_dates) > MIN_HISTORY:
    start_date = stock_dates[MIN_HISTORY]
else:
    start_date = stock_dates[0]
trade_dates = [d for d in trade_dates if d >= pd.Timestamp(start_date)]
# 每5天取一个日期
step = max(1, len(trade_dates) // 25)  # 目标约25个采样点
trade_dates = trade_dates[::step]
print(f"分析日期(抽样): {trade_dates[0].strftime('%Y-%m-%d')} ~ {trade_dates[-1].strftime('%Y-%m-%d')} ({len(trade_dates)}天)")

# ============ 初始化策略（注册所有因子） ============
print("初始化因子引擎...")
strategy = MultiFactorStrategy()
engine = strategy.engine
factor_names = list(engine.factors.keys())
print(f"已注册 {len(factor_names)} 个因子: {', '.join(factor_names[:8])}...")

# ============ 计算横截面因子值（逐日） ============
print("计算横截面因子值...")
factor_records = []
return_records = []

for di, date in enumerate(trade_dates):
    if (di + 1) % 20 == 0:
        print(f"  进度: {di+1}/{len(trade_dates)} ({date.strftime('%m-%d')})")

    for code, df_all in data_dict.items():
        mask = df_all['date'] <= pd.Timestamp(date)
        if mask.sum() < MIN_HISTORY:
            continue
        df_u = df_all[mask]
        rec = {'date': date, 'code': code}
        all_nan = True
        for fname in factor_names:
            f = engine.factors.get(fname)
            if f is None:
                rec[fname] = np.nan
                continue
            try:
                v = f.get_latest(df_u)
            except Exception:
                v = np.nan
            if isinstance(v, (list, pd.Series, np.ndarray)):
                try:
                    v = float(v)
                except Exception:
                    v = np.nan
            rec[fname] = v if pd.notna(v) else np.nan
            if pd.notna(rec[fname]):
                all_nan = False
        if all_nan:
            continue
        factor_records.append(rec)
        return_records.append({'date': date, 'code': code, 'close': float(df_u['close'].iloc[-1])})

factor_df = pd.DataFrame(factor_records)
return_df = pd.DataFrame(return_records)
print(f"因子数据: {factor_df.shape} (行={len(factor_df)}, 因子列={len(factor_names)})")

# ============ IC/IR 分析 ============
print("\n" + "="*60)
print("IC/IR 分析中...")
print("="*60)

# 先算每只股票的未来收益
merged = return_df.merge(factor_df, on=['date', 'code'], how='inner')
merged = merged.sort_values(['code', 'date'])
for p in PERIODS:
    merged[f'fwd_ret_{p}'] = merged.groupby('code')['close'].pct_change(p).shift(-p)

# 逐因子、逐周期计算 IC
ic_results = []
quantile_results = []

valid_factors = []
for fname in factor_names:
    if fname not in merged.columns:
        continue
    n_non_null = merged[fname].notna().sum()
    if n_non_null < 100:
        continue
    valid_factors.append(fname)

print(f"有效因子: {len(valid_factors)}/{len(factor_names)} 个")

for fi, fname in enumerate(valid_factors):
    print(f"\n[{fi+1}/{len(valid_factors)}] {fname}...")

    # IC 计算
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

    # 分组收益分析 (5日)
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
            groups_ret.append({
                'date': date,
                'long': gr[4], 'short': gr[0],
                'long_short': gr[4] - gr[0],
            })
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
    # 按 5日 IR 排序，找最强因子
    ic5 = ic_df[ic_df['周期'] == '5日'].sort_values('IR', ascending=False)
    print("\n" + "="*60)
    print("=== 因子有效性排名 (5日周期, 按IR排序) ===")
    print("="*60)
    print(ic5.to_string(index=False))

    # 汇总每个因子的最佳周期
    print("\n" + "="*60)
    print("=== 各因子最佳周期汇总 ===")
    print("="*60)
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
