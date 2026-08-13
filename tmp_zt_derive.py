"""
验证：用日线数据推导涨停家数，与AKShare真实涨停数对比
思路：主板涨停 = 涨幅>=9.8% 且 close≈high（一字/封板）
用现有166天全市场K线（4399只）推导，对比最近30天AKShare真实涨停数
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np
import os, gc
from config import DAILY_DIR

# 只用短历史(<=30KB)的全市场票做验证，避免OOM
files = [f for f in os.listdir(DAILY_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DAILY_DIR, f)) <= 30000]
print(f'全市场短历史票: {len(files)} 只')

# 逐票累加每天的涨停标记，用日期字典存 {date: count}
# 但先只测最近30天，减少内存
from datetime import datetime, timedelta

# 目标日期范围（AKShare有真实数据的最近30天）
target_dates = set()
d = datetime(2026, 8, 12)
for i in range(35):
    target_dates.add((d - timedelta(days=i)).strftime('%Y-%m-%d'))

# 涨停计数 {date: 涨停家数}
zt_count = {}
zhaban_count = {}  # 曾触涨停但没封住（盘中最高>=9.8%但收盘<9.8%）

for idx, f in enumerate(files):
    code = f[:-4]
    # 判断板块：主板 60/00 涨停10%，创业板30 20%，科创68 20%
    if code.startswith('30') or code.startswith('68'):
        limit = 0.198
    else:
        limit = 0.098
    try:
        df = pd.read_csv(os.path.join(DAILY_DIR, f))
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df['pct_chg'] = df['close'] / df['close'].shift(1) - 1
        # 最近35天
        df = df[df['date'] >= '2026-07-01']
        for _, row in df.iterrows():
            ds = row['date'].strftime('%Y-%m-%d')
            if ds not in target_dates:
                continue
            pct = row['pct_chg']
            if pd.isna(pct):
                continue
            # 盘中最高涨幅
            intraday_high_pct = row['high'] / (row['close'] / (1 + pct)) - 1
            # 涨停：收盘涨幅达到阈值
            if pct >= limit:
                zt_count[ds] = zt_count.get(ds, 0) + 1
            # 炸板：盘中触及涨停但收盘没封住
            elif intraday_high_pct >= limit and pct < limit:
                zhaban_count[ds] = zhaban_count.get(ds, 0) + 1
    except Exception as e:
        pass
    del df
    gc.collect()
    if (idx+1) % 1000 == 0:
        print(f'  进度 {idx+1}/{len(files)}')

print('\n=== 推导结果（最近交易日） ===')
for ds in sorted(zt_count.keys()):
    print(f'  {ds}: 涨停{zt_count.get(ds,0)} 炸板{zhaban_count.get(ds,0)}')
