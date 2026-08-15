# -*- coding: utf-8 -*-
"""用 akshare 验证 000006 在 8/13 是否涨停"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import akshare as ak
import pandas as pd

# 直接查 8/13 涨停池
ak_zt = ak.stock_zt_pool_em(date='20260813')
zt_codes = set(ak_zt['代码'].astype(str).tolist())
print(f'8/13 akshare涨停池: {len(zt_codes)} 只')
print(f'000006 在涨停池: {"000006" in zt_codes}')
print(f'000593 在涨停池: {"000593" in zt_codes}')

# 查 000006 的日线
print()
print('=== 000006 日线（akshare）===')
try:
    df = ak.stock_zh_a_hist(symbol='000006', period='daily', start_date='20260810', end_date='20260813', adjust='')
    print(df[['日期','开盘','最高','最低','收盘','涨跌幅']].to_string(index=False))
except Exception as e:
    print(f'失败: {e}')

print()
print('=== 000593 日线 ===')
try:
    df2 = ak.stock_zh_a_hist(symbol='000593', period='daily', start_date='20260810', end_date='20260813', adjust='')
    print(df2[['日期','开盘','最高','最低','收盘','涨跌幅']].to_string(index=False))
except Exception as e:
    print(f'失败: {e}')

# 核心问题：stock_pool 里有多少 688 开头的
print()
pool = pd.read_csv('data/stock_pool.csv')
pool_codes = pool['code'].astype(str).str.zfill(6)
print(f'stock_pool 总数: {len(pool_codes)}')
print(f'688开头: {(pool_codes.str.startswith("688")).sum()}')
print(f'300开头: {(pool_codes.str.startswith("300")).sum()}')
print(f'301开头: {(pool_codes.str.startswith("301")).sum()}')

# 688137, 688265 是否在 pool
print(f'688137 在pool: {"688137" in set(pool_codes.tolist())}')
print(f'688265 在pool: {"688265" in set(pool_codes.tolist())}')

# 看 stock_pool 的构成
print()
print('=== stock_pool 板块分布 ===')
prefix = pool_codes.str[:3]
print(prefix.value_counts().to_string())
