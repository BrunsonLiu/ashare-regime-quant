"""
扩池验证：181只资源类股票(3年长历史)，右侧放量埋伏信号全量扫描
目的：验证"低位+跌透+放量阳线"的alpha是"周期运气"还是"普适规律"
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
import gc
from config import DAILY_DIR

# 只读长历史(>30KB)的资源票
def get_long_hist_codes():
    codes = []
    for f in os.listdir(DAILY_DIR):
        if not f.endswith('.csv'):
            continue
        path = os.path.join(DAILY_DIR, f)
        if os.path.getsize(path) > 30000:
            codes.append(f[:-4])
    return codes

codes = get_long_hist_codes()
print(f'[OK] 长历史资源票 {len(codes)} 只')

all_signals = []

for idx, code in enumerate(codes):
    path = os.path.join(DAILY_DIR, code + '.csv')
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    close = df['close'].values
    high = df['high'].values
    vol = df['volume'].values
    n = len(df)

    vol_ma5 = pd.Series(vol).rolling(5).mean().values

    for i in range(120, n):
        # 低位：距250日高点回撤>25%
        high_250 = high[max(0, i-250):i+1].max()
        cur = close[i]
        dd = (cur - high_250) / high_250
        if dd > -0.25:
            continue
        # 跌透：60日跌幅 > -6%
        chg60 = (cur / close[i-60] - 1)
        if chg60 < -0.06:
            continue
        # 右侧：放量阳线（量>5日均1.5倍，涨>1%）
        today_vol = vol[i]
        vma5 = vol_ma5[i]
        today_chg = (close[i] / close[i-1] - 1)
        if not (today_vol > vma5 * 1.5 and today_chg > 0.01):
            continue

        # 未来收益
        f20 = (close[i+20]/cur - 1)*100 if i+20 < n else np.nan
        f60 = (close[i+60]/cur - 1)*100 if i+60 < n else np.nan
        all_signals.append({
            'code': code, 'date': df['date'].iloc[i],
            'f20': f20, 'f60': f60,
            'chg60': round(chg60*100, 1), 'dd': round(dd*100, 1),
        })

    del df
    gc.collect()
    if (idx+1) % 50 == 0:
        print(f'  进度 {idx+1}/{len(codes)}，累计信号 {len(all_signals)}')

sig = pd.DataFrame(all_signals)
print(f'\n=== 扩池验证结果：{len(codes)}只资源票，{len(sig)}次右侧信号 ===\n')

# 按年份分组看收益（判断是否周期依赖）
sig['year'] = sig['date'].dt.year
for year in sorted(sig['year'].unique()):
    sub = sig[sig['year'] == year]
    f20 = sub['f20'].dropna()
    f60 = sub['f60'].dropna()
    print(f'{year}年: 信号{len(sub)} | 20日均{np.mean(f20):+.1f}% 胜率{np.mean(f20>0)*100:.0f}% | 60日均{np.mean(f60):+.1f}% 胜率{np.mean(f60>0)*100:.0f}%')

print()
f20 = sig['f20'].dropna()
f60 = sig['f60'].dropna()
print(f'全样本: 20日均{np.mean(f20):+.1f}% 中位{np.median(f20):+.1f}% 胜率{np.mean(f20>0)*100:.0f}%')
print(f'全样本: 60日均{np.mean(f60):+.1f}% 中位{np.median(f60):+.1f}% 胜率{np.mean(f60>0)*100:.0f}%')
