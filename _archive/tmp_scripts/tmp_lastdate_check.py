# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

z = pd.read_csv('data/zt_events.csv', header=None, dtype={1: str}, names=['date','code','lb'])
z['date'] = pd.to_datetime(z['date'])

# 每只股票最后一条涨停记录的日期
last = z.groupby('code')['date'].max()
print('=== 各股票"最后涨停记录日期"分布 ===')
print(last.dt.date.value_counts().sort_index().tail(15).to_string())

# 08-13 涨停的股票，它们的"最后记录日期"是否都集中在08-13附近
d13 = z[z['date'] == '2026-08-13']
print('\n08-13 涨停', len(d13), '只，代码:')
print(sorted(d13['code'].tolist()))

# 这些 08-13 涨停股，在 08-12 是否也涨停（连板）
d12 = z[z['date'] == '2026-08-12']
print('\n08-12 涨停', len(d12), '只')

# 关键：08-13 涨停的股，它的连板数是多少
print('\n08-13 涨停股连板数分布:')
print(d13['lb'].value_counts().sort_index().to_string())

# 对照 akshare 全市场 08-13 涨停 59 只
print('\n=== 结论: zt_events 08-13 仅', len(d13), '条 vs 全市场实际约59只涨停 ===')
