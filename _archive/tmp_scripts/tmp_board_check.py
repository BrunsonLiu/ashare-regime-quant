# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

def board(c):
    s = str(c).zfill(6)
    if s.startswith('60'):
        return '沪主板'
    if s.startswith(('000', '001', '002', '003')):
        return '深主板'
    if s.startswith(('300', '301')):
        return '创业板'
    if s.startswith(('688', '689')):
        return '科创板'
    if s.startswith(('8', '4', '92')):
        return '北交所'
    return '其他:' + s[:3]

# 股票池
p = pd.read_csv('data/stock_pool.csv')
print('=== stock_pool.csv 板块组成 ===')
print(p['code'].astype(str).apply(board).value_counts().to_string())

# zt_events 原始文件（补零字符串）
z = pd.read_csv('data/zt_events.csv', header=None, dtype={1: str})
print('\n=== zt_events.csv 板块组成 ===')
print(z[1].apply(board).value_counts().to_string())

# 只看主板（60+00）
zz = z[1].apply(board)
mainboard = zz.isin(['沪主板', '深主板'])
print('\n主板涨停事件:', mainboard.sum(), '/', len(z))
