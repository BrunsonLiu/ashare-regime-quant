import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from config import DAILY_DIR
from src.sentiment.supply_chain import get_all_upstream_stocks

upstream = get_all_upstream_stocks(("60", "00"))

print("=== 上游标的历史走势形态分析（判断是否有过横盘企稳）===\n")

for s in upstream:
    code = s["code"]
    path = os.path.join(DAILY_DIR, code + ".csv")
    if not os.path.exists(path):
        continue
    df = pd.read_csv(path)
    df = df.sort_values('date').reset_index(drop=True)
    c = df['close'].values
    n = len(c)

    # 分段：把165天分成3段，看每段走势
    seg = n // 3
    seg1 = (c[seg] / c[0] - 1) * 100
    seg2 = (c[2*seg] / c[seg] - 1) * 100
    seg3 = (c[-1] / c[2*seg] - 1) * 100

    # 近20日横盘检测
    recent20 = df.tail(20)
    rng = (recent20['high'].max() - recent20['low'].min()) / recent20['low'].min() * 100

    # 近60日是否下跌
    chg60 = (c[-1] / c[-60] - 1) * 100 if n >= 60 else 0

    print(f"{code} {s['name']:8s} | 3段涨幅: {seg1:+6.1f}% {seg2:+6.1f}% {seg3:+6.1f}% | 近60日:{chg60:+6.1f}% | 近20日区间宽:{rng:.1f}%")
