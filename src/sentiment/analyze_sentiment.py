# -*- coding: utf-8 -*-
import sys, os
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV = os.path.join(ROOT, 'data', 'sentiment_3y.csv')

df = pd.read_csv(CSV, parse_dates=['date'])
df = df.sort_values('date').reset_index(drop=True)

print('=== 总体统计 (%.0f天, %s ~ %s) ===' % (len(df), df.date.min().date(), df.date.max().date()))
print()
for c in ['zt_count', 'zhaban_rate', 'lianban_height', 'shouban_ratio']:
    print('%-14s mean=%7.2f  median=%7.2f  std=%7.2f  min=%6.2f  max=%6.2f' % (
        c, df[c].mean(), df[c].median(), df[c].std(), df[c].min(), df[c].max()))

print()
print('=== 分位数 ===')
for c in ['zt_count', 'zhaban_rate', 'lianban_height']:
    q = df[c].quantile([0.1, 0.2, 0.25, 0.5, 0.75, 0.8, 0.9]).round(2)
    print(c, q.to_dict())

zt_low = df['zt_count'].quantile(0.2)
zh_high = df['zhaban_rate'].quantile(0.8)
print()
print('冰点阈值: zt_count < %.0f  或  zhaban_rate > %.3f' % (zt_low, zh_high))

# 冰点 / 高潮 标记
df['is_bing'] = ((df['zt_count'] < zt_low) | (df['zhaban_rate'] > zh_high)).astype(int)
df['is_gao'] = (df['zt_count'] > df['zt_count'].quantile(0.8)).astype(int)

print()
print('=== 月度情绪 (mean) ===')
df['ym'] = df['date'].dt.to_period('M')
m = df.groupby('ym').agg(
    涨停=('zt_count', 'mean'),
    炸板率=('zhaban_rate', 'mean'),
    连板高度=('lianban_height', 'mean'),
    首板占比=('shouban_ratio', 'mean'),
    交易日=('date', 'count'),
    冰点天数=('is_bing', 'sum'),
).round(3)
print(m.to_string())

print()
print('=== 年度情绪 ===')
df['year'] = df['date'].dt.year
y = df.groupby('year').agg(
    涨停均值=('zt_count', 'mean'),
    炸板率=('zhaban_rate', 'mean'),
    连板高度=('lianban_height', 'mean'),
    冰点天数=('is_bing', 'sum'),
    交易日=('date', 'count'),
).round(3)
print(y.to_string())

print()
print('=== 冰点日列表 (zt<%.0f 或 炸板率>%.2f) ===' % (zt_low, zh_high))
bing = df[df['is_bing'] == 1]
print('共 %d 个冰点日' % len(bing))
if len(bing) > 0:
    print(bing[['date', 'zt_count', 'zhaban_rate', 'lianban_height']].to_string(index=False))

print()
print('=== 高潮日列表 (zt>%.0f) ===' % df['zt_count'].quantile(0.8))
gao = df[df['is_gao'] == 1]
print('共 %d 个高潮日' % len(gao))
if len(gao) > 0:
    print(gao[['date', 'zt_count', 'zhaban_rate', 'lianban_height']].to_string(index=False))

# 连板高度分布
print()
print('=== 连板高度分布 ===')
print(df['lianban_height'].value_counts().sort_index().to_string())

# 当前状态
print()
print('=== 最近10个交易日 ===')
print(df.tail(10)[['date', 'zt_count', 'zhaban_rate', 'lianban_height', 'shouban_ratio', 'is_bing']].to_string(index=False))
