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

print('=== 最近10个交易日 zt_events 板块分布 ===')
for d in sorted(z['date'].unique())[-10:]:
    sub = z[z['date'] == d]
    print(f'\n{d}: 共{len(sub)}只')
    print(sub['b'].value_counts().to_dict())
