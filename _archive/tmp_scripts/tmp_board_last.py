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

# 各板块股票"最后涨停记录日期"分布（看是否深主板系统性缺失 08-13）
for bname in ['沪主板', '深主板', '创业板']:
    sub = z[z['b'] == bname]
    last = sub.groupby('code')['date'].max()
    tail = last.value_counts().sort_index().tail(6)
    print(f'=== {bname} 股票最后涨停日期分布(近6天) ===')
    print(tail.to_string())
    print()

# 直接看：08-13 当天，深主板应该有多少只股票被"处理过"
# 用 zt_done.txt 的 code 顺序推断
done = open('data/zt_done.txt', encoding='utf-8').read().splitlines()
done = [x.strip() for x in done if x.strip()]
print('zt_done 前10只(最早处理):', done[:10])
print('zt_done 后10只(最晚处理):', done[-10:])
