"""
对比不同"右侧确认"定义的收益，找出最优右侧信号
候选定义：
  A. 放量+突破20日高（当前，太严）
  B. 放量阳线（量>5日均1.5倍，涨>1%，不要求突破）
  C. 放量阳线 + 前5日缩量（缩量止跌后放量）
  D. 量>5日均2倍 大涨>3%（强启动）
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from config import DAILY_DIR
from src.sentiment.supply_chain import get_all_upstream_stocks

upstream = get_all_upstream_stocks(("60", "00"))

results = {}

for s in upstream:
    code = s["code"]
    path = os.path.join(DAILY_DIR, code + ".csv")
    if not os.path.exists(path):
        continue
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    close = df['close'].values
    high = df['high'].values
    vol = df['volume'].values
    n = len(df)

    vol_ma5 = pd.Series(vol).rolling(5).mean().values

    for i in range(120, n):
        # 前置条件：低位 + 跌透（与检测器一致）
        high_250 = high[max(0,i-250):i+1].max()
        cur = close[i]
        dd = (cur - high_250) / high_250
        if dd > -0.25:  # 不是低位
            continue
        if i >= 60:
            chg60 = (cur / close[i-60] - 1)
            if chg60 < -0.06:  # 还在跌
                continue

        today_chg = (close[i] / close[i-1] - 1) if i >= 1 else 0
        today_vol = vol[i]
        vma5 = vol_ma5[i]

        # 定义A：放量+突破20日高
        prev_high20 = high[i-20:i].max() if i >= 20 else high[:i].max()
        A = today_vol > vma5 * 1.5 and today_chg > 0.01 and close[i] > prev_high20

        # 定义B：放量阳线（不要求突破）
        B = today_vol > vma5 * 1.5 and today_chg > 0.01

        # 定义C：缩量止跌后放量阳线（前5日量<60日均0.45）
        vol_ma60 = pd.Series(vol).rolling(60).mean().values
        prev_shrink = vol_ma60[i] > 0 and vol_ma5[i-1] < vol_ma60[i] * 0.45 if i >= 1 else False
        C = B and prev_shrink

        # 定义D：放量大涨
        D = today_vol > vma5 * 2.0 and today_chg > 0.03

        for name, cond in [("A_breakout", A), ("B_volume", B), ("C_shrink_surge", C), ("D_strong", D)]:
            if not cond:
                continue
            if name not in results:
                results[name] = []
            # 计算未来20/60日收益
            f20 = (close[i+20]/cur - 1)*100 if i+20 < n else np.nan
            f60 = (close[i+60]/cur - 1)*100 if i+60 < n else np.nan
            results[name].append({'code': code, 'date': df['date'].iloc[i], 'f20': f20, 'f60': f60})

print("=== 不同右侧确认定义的收益对比 ===\n")
for name in ["A_breakout", "B_volume", "C_shrink_surge", "D_strong"]:
    rs = results.get(name, [])
    if not rs:
        print(f"[{name}] 无信号")
        continue
    f20 = [r['f20'] for r in rs if not np.isnan(r['f20'])]
    f60 = [r['f60'] for r in rs if not np.isnan(r['f60'])]
    print(f"[{name}] 样本{len(rs)}")
    print(f"  20日: 均值{np.mean(f20):+.1f}% 中位{np.median(f20):+.1f}% 胜率{np.mean(np.array(f20)>0)*100:.0f}%")
    print(f"  60日: 均值{np.mean(f60):+.1f}% 中位{np.median(f60):+.1f}% 胜率{np.mean(np.array(f60)>0)*100:.0f}%")
    print()
