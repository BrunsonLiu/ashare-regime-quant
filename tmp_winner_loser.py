import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from config import DAILY_DIR

# 对比：赢家(600111北方稀土) vs 输家(600399抚顺特钢/000970中科三环/600366宁波韵升)
# 看买入前60天的量价特征，找"会爆发"的伏击点特征

def analyze(code, name, buy_date):
    df = pd.read_csv(os.path.join(DAILY_DIR, code + '.csv'))
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'] <= buy_date].tail(80)  # 买入前80天

    close = df['close'].values
    vol = df['volume'].values
    n = len(close)

    # 买入前20日 vs 前60日的量价
    vol_5 = vol[-5:].mean()
    vol_60 = vol[:-5].mean() if n > 5 else vol.mean()

    # 买入前60日涨幅
    chg60 = (close[-1] / close[-60] - 1) * 100 if n >= 60 else 0

    # 底部横盘时间（距低点天数）
    low_idx = np.argmin(close)
    days_from_low = n - 1 - low_idx

    # 量能萎缩程度
    vol_shrink = vol_5 / vol_60

    print(f"{code} {name} 买入日{buy_date}")
    print(f"  买入前60日涨幅: {chg60:+.1f}%")
    print(f"  距60日低点: {days_from_low}天")
    print(f"  近5日均量/前均量: {vol_shrink:.2f}")
    print(f"  近20日区间: {df['low'].tail(20).min():.2f}~{df['high'].tail(20).max():.2f}")
    print()

print("=== 赢家 vs 输家 伏击点特征对比 ===\n")

analyze("600111", "北方稀土", "2025-12-19")   # 赢家 +36.8%
analyze("600399", "抚顺特钢", "2026-04-20")   # 输家 -11%
analyze("000970", "中科三环", "2026-04-08")   # 输家 +5.5%(时间止损)
analyze("600366", "宁波韵升", "2026-04-07")   # 输家 +6.5%(时间止损)
