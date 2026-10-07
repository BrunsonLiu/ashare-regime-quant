# -*- coding: utf-8 -*-
"""拉取超长历史(默认2014起≈12年, 覆盖多轮完整牛熊)用于最严格的跨周期验证
用法: python scripts/fetch_ultra_long.py [n_stocks] [start_date]
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
    n_stocks = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    start = sys.argv[2] if len(sys.argv) > 2 else '2014-01-01'
    pool = pd.read_csv(os.path.join(ROOT, 'data', 'stock_pool.csv'))
    codes = [str(c).zfill(6) for c in pool['code']][:n_stocks]
    print(f'拉取 {len(codes)} 只 × {start}起(超长历史)...', flush=True)

    loader = DataLoader()
    ok = 0
    t0 = time.time()
    for i, c in enumerate(codes):
        try:
            df = loader.get_daily_data(c, days=4600)   # 4600日历天≈12.6年
            if df is not None and len(df) > 1500:
                ok += 1
        except Exception:
            pass
        if (i + 1) % 25 == 0:
            print(f'  {i+1}/{len(codes)} ok={ok} {time.time()-t0:.0f}s', flush=True)
    print(f'完成: {ok}/{len(codes)} 只获得超长历史(>1500行)', flush=True)


if __name__ == '__main__':
    main()
