import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from src.sentiment.lurk_detector import LurkDetector

def make_data(pattern):
    """生成250天合成日线"""
    dates = pd.date_range('2025-01-01', periods=250, freq='B')
    n = 250
    close = np.zeros(n)
    if pattern == "lurk_ready":
        # 下跌→缩量横盘企稳（理想埋伏形态）
        close[:100] = np.linspace(30, 20, 100)      # 下跌
        close[100:230] = 20 + np.random.normal(0, 0.2, 130)  # 缩量横盘
        close[230:] = 20 + np.random.normal(0, 0.15, 20)
    elif pattern == "still_falling":
        # 持续阴跌
        close = np.linspace(30, 10, 250) + np.random.normal(0, 0.3, 250)
    elif pattern == "high_position":
        # 高位震荡
        close = 30 + np.random.normal(0, 0.5, 250)

    volume = np.ones(n) * 1e6
    # 横盘期缩量
    if pattern == "lurk_ready":
        volume[100:] = 3e5  # 缩量持续到底
    volume = volume * (1 + np.random.normal(0, 0.1, n))

    high = close * 1.01
    low = close * 0.99
    open_ = close * 0.995

    df = pd.DataFrame({
        'date': dates, 'open': open_, 'high': high, 'low': low,
        'close': close, 'volume': volume, 'amount': volume * close,
    })
    return df

detector = LurkDetector()
print("=== 合成数据验证检测器逻辑 ===\n")

for pattern, label in [("lurk_ready", "下跌→缩量横盘企稳(理想埋伏)"),
                        ("still_falling", "持续阴跌(不该买)"),
                        ("high_position", "高位震荡(不该买)")]:
    df = make_data(pattern)
    r = detector.detect_low_position("TEST", label, df)
    status = "符合埋伏" if r["eligible"] else "不符合"
    print(f"[{label}]")
    print(f"  判定: {status} | 评分={r['score']}/10")
    print(f"  位置={r['position_state']} 量能={r['volume_state']} 横盘={r['consolidating']}")
    print(f"  买入方式={r['buy_mode']}")
    print(f"  信号: {'; '.join(r['signals'])}")
    print()
