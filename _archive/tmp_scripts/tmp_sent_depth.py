"""
侦察：情绪数据的历史深度
1. 涨停池 stock_zt_pool_em 能回填多久
2. 炸板池 stock_zt_pool_zbgc_em 历史
3. 强势涨停 stock_zt_pool_strong_em 历史
4. 北向资金历史长度
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import akshare as ak
import pandas as pd

# 1. 涨停池：测几个历史日期
print("=== 涨停池历史深度测试 ===")
for d in ['20260731', '20260601', '20260501', '20260401', '20260301', '20260101', '20250701', '20250101']:
    try:
        df = ak.stock_zt_pool_em(date=d)
        print(f'  {d}: {len(df)}只')
    except Exception as e:
        print(f'  {d}: [X] {e}')

print()
print("=== 炸板池历史 ===")
for d in ['20260731', '20260601', '20260101']:
    try:
        df = ak.stock_zt_pool_zbgc_em(date=d)
        print(f'  {d}: {len(df)}只')
    except Exception as e:
        print(f'  {d}: [X] {e}')

print()
print("=== 强势涨停历史 ===")
for d in ['20260731', '20260601', '20260101']:
    try:
        df = ak.stock_zt_pool_strong_em(date=d)
        print(f'  {d}: {len(df)}只')
    except Exception as e:
        print(f'  {d}: [X] {e}')
