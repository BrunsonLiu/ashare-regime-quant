# -*- coding: utf-8 -*-
import pandas as pd, numpy as np

df = pd.read_csv('data/sentiment_3y.csv', parse_dates=['date']).sort_values('date').reset_index(drop=True)

df['zt_ma5'] = df.zt_count.rolling(5).mean()
df['zt_ma20'] = df.zt_count.rolling(20).mean()
df['rate_ma5'] = df.zhaban_rate.rolling(5).mean()

zt_p20 = df.zt_count.quantile(0.20)
zt_p40 = df.zt_count.quantile(0.40)
print(f'涨停家数分位: p20={zt_p20:.0f}  p40={zt_p40:.0f}  p50={df.zt_count.median():.0f}')

# 冰点定义
ice = df[(df.zt_count <= zt_p20) | ((df.zt_count <= 30) & (df.lianban_height <= 3))].copy()
print(f'\n=== 冰点交易日 (共{len(ice)}天) ===')
print(ice[['date','zt_count','zhaban_count','zhaban_rate','lianban_height']].to_string(index=False))

# 退潮期: 涨停家数连续3日下滑 或 炸板率>0.5 且 涨停数<均值
df['zt_chg'] = df.zt_count.diff()
retreat = []
for i in range(2, len(df)):
    w = df.iloc[i-2:i+1]
    if (w.zt_chg.iloc[1] < 0 and w.zt_chg.iloc[2] < 0) and w.zt_count.iloc[2] < df.zt_count.median():
        retreat.append((df.date.iloc[i], df.zt_count.iloc[i], df.zhaban_rate.iloc[i], df.lianban_height.iloc[i]))
print(f'\n=== 退潮信号 (连续2日涨停下滑且低于中位) 共{len(retreat)}次 ===')
for r in retreat[:40]:
    print(f'{r[0].date()}  zt={r[1]:3d}  rate={r[2]:.2f}  h={r[3]}')

# 高潮期: 涨停 >= p80 且 高度>=8
zt_p80 = df.zt_count.quantile(0.80)
boom = df[(df.zt_count >= zt_p80) & (df.lianban_height >= 8)].copy()
print(f'\n=== 高潮交易日 (涨停>={zt_p80:.0f} 且 高度>=8) 共{len(boom)}天 ===')
print(boom[['date','zt_count','zhaban_rate','lianban_height','lianban4p']].to_string(index=False))
