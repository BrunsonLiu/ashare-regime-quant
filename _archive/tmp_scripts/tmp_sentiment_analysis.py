# -*- coding: utf-8 -*-
import pandas as pd, numpy as np

df = pd.read_csv('data/sentiment_3y.csv', parse_dates=['date']).sort_values('date').reset_index(drop=True)
print('范围:', df.date.min().date(), '->', df.date.max().date(), '共', len(df), '天')

print('\n=== 全样本分布 ===')
for c in ['zt_count','zhaban_count','zhaban_rate','lianban_height','lianban2','lianban3','lianban4p','shouban','shouban_ratio']:
    s = df[c]
    print(f'{c:15s} mean={s.mean():.3f} med={s.median():.3f} std={s.std():.3f} min={s.min():.2f} p25={s.quantile(.25):.2f} p75={s.quantile(.75):.2f} max={s.max():.2f}')

# 冰点：涨停家数低 + 炸板率高
zt_low = df.zt_count.quantile(.2)
zhaban_high = df.zhaban_rate.quantile(.8)
ice = df[(df.zt_count <= zt_low) & (df.zhaban_rate >= zhaban_high)]
print(f'\n=== 冰点识别 (zt<={zt_low:.0f} 且 炸板率>={zhaban_high:.2f}) 共{len(ice)}天 ===')
print('冰点样本(近15):')
print(ice.tail(15)[['date','zt_count','zhaban_rate','lianban_height']].to_string(index=False))

# 高潮：连板高度>=5
hot = df[df.lianban_height >= 5]
print('\n=== 连板高度>=5 高潮日 共%d天 ===' % len(hot))
print(hot.tail(15)[['date','zt_count','zhaban_rate','lianban_height','lianban2','lianban3','lianban4p']].to_string(index=False))

# 按年度统计
print('\n=== 按年统计 ===')
df['year'] = df.date.dt.year
for y, g in df.groupby('year'):
    print(f'{y}: 交易日{g.zt_count.count()}天, 涨停均值{g.zt_count.mean():.1f}, 炸板率均值{g.zhaban_rate.mean():.3f}, 最高连板{g.lianban_height.max():.0f}')

# 月度统计
print('\n=== 按月(近12月) ===')
df['ym'] = df.date.dt.to_period('M')
recent = df[df.date >= '2025-08-01']
for ym, g in recent.groupby('ym'):
    print(f'{ym}: 涨停均值{g.zt_count.mean():.1f}, 炸板率均值{g.zhaban_rate.mean():.3f}, 最高连板{g.lianban_height.max():.0f}, 交易日{len(g)}')

# 近期最新状态
print('\n=== 最新5个交易日 ===')
print(df.tail(5)[['date','zt_count','zhaban_count','zhaban_rate','lianban_height','lianban2','lianban3','lianban4p','shouban_ratio']].to_string(index=False))
