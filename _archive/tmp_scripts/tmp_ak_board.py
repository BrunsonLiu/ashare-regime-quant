# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import akshare as ak
import pandas as pd

for dt in ['20260813', '20260814']:
    try:
        df = ak.stock_zt_pool_em(date=dt)
        print(f'=== {dt} 全市场涨停 {len(df)} 只 ===')
        codes = df['代码'].astype(str).str.zfill(6)
        def board(c):
            if c.startswith('60'): return '沪主板'
            if c.startswith(('000','001','002','003')): return '深主板'
            if c.startswith(('300','301')): return '创业板'
            if c.startswith(('688','689')): return '科创板'
            if c.startswith(('8','4','92')): return '北交所'
            return '其他'
        print(codes.apply(board).value_counts().to_string())
        print()
    except Exception as e:
        print(dt, '失败', repr(e)[:150])
