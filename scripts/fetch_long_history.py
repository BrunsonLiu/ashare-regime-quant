# -*- coding: utf-8 -*-
"""一次性: 拉长历史日线(默认1300日历天≈3.5年) 覆盖多个牛熊周期
用法: python scripts/fetch_long_history.py [n_stocks] [days]
"""
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8')

from src.data_loader import DataLoader


def main():
    n_stocks = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 1300
    pool = pd.read_csv(os.path.join(ROOT, 'data', 'stock_pool.csv'))
    codes = [str(c).zfill(6) for c in pool['code']][:n_stocks]
    print(f'拉取 {len(codes)} 只 × {days}日历天 日线...', flush=True)

    loader = DataLoader()
    ok = 0
    t0 = time.time()
    for i, c in enumerate(codes):
        try:
            df = loader.get_daily_data(c, days=days)
            if df is not None and len(df) > 400:   # 至少约1.5年才算成功
                ok += 1
        except Exception:
            pass
        if (i + 1) % 50 == 0:
            print(f'  进度 {i+1}/{len(codes)} ok={ok} 用时{time.time()-t0:.0f}s', flush=True)
    print(f'完成: {ok}/{len(codes)} 只获得长历史(>{days}天)', flush=True)


if __name__ == '__main__':
    main()
