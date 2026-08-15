# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

z = pd.read_csv('data/zt_events.csv', header=None, dtype={1: str}, names=['date','code','lb'])

def board(c):
    if c.startswith('60'): return '沪主板'
    if c.startswith(('000','001','002','003')): return '深主板'
    if c.startswith(('300','301')): return '创业板'
    if c.startswith(('688','689')): return '科创板'
    return '其他'

z['b'] = z['code'].apply(board)

# 每月深主板涨停事件数
z['ym'] = z['date'].str[:7]
pivot = z.pivot_table(index='ym', columns='b', values='code', aggfunc='count', fill_value=0)
print('=== 每月各板块涨停事件数 ===')
print(pivot.to_string())

# 计算深主板"缺失比例"：创业板/沪主板 是深主板的多少倍
print('\n=== 沪主板/深主板 比值 ===')
pivot['沪/深'] = (pivot['沪主板'] / pivot['深主板']).round(2)
print(pivot[['沪主板','深主板','创业板','沪/深']].to_string())
