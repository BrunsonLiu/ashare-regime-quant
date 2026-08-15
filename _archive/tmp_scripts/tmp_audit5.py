# -*- coding: utf-8 -*-
"""code 格式问题：000006 被存成 6"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

zt = pd.read_csv('data/zt_events.csv', names=['date','code','lianban'])
zb = pd.read_csv('data/zhaban_events.csv', names=['date','code'])

print('=== zt_events code 格式检查 ===')
print(f'code dtype: {zt["code"].dtype}')
print(f'code 样例(前20个unique): {sorted(zt["code"].unique())[:20]}')
print(f'code 最大值: {zt["code"].max()}')
print(f'code 最小值: {zt["code"].min()}')

# 检查有多少 code 不足6位
zt_str = zt['code'].astype(str)
short = zt_str[zt_str.str.len() < 6]
print(f'code不足6位的行数: {len(short)} ({len(short)/len(zt)*100:.1f}%)')

# 检查 000006 在 8/13 的记录
r = zt[(zt['code'] == 6) & (zt['date'] == '2026-08-13')]
print(f'\n000006 (存为6) 在 2026-08-13: {len(r)} 条')
r2 = zt[(zt['code'].astype(str).str.zfill(6) == '000006') & (zt['date'] == '2026-08-13')]
print(f'zfill(6)后查 000006 在 2026-08-13: {len(r2)} 条')

# 关键：worker 写入的是 int(code)，前导零被丢了
# 但 aggregate_sentiment 用 groupby('date').size() 聚合，code 格式不影响 zt_count
# 所以 zt_count 应该是正确的——问题在于 code 列本身的完整性

# 验证：8/13 实际 zt_events 中有多少行
zt_0813 = zt[zt['date'] == '2026-08-13']
print(f'\n2026-08-13 zt_events 行数: {len(zt_0813)}')
print(f'sentiment_3y 中 8/13 zt_count: ', end='')
s = pd.read_csv('data/sentiment_3y.csv')
print(s[s['date']=='2026-08-13']['zt_count'].values[0])

# 所以 28 是正确的——000006 在 zt_events 里有，只是 code 存成了 6
# 那为什么之前交叉验证说 akshare 59 vs baostock 28？
# 重新做：用 zfill(6) 后比较
ak_only_in_zt = zt[(zt['date'] == '2026-08-13') & (zt['code'].astype(str).str.zfill(6).isin(['000006','000593','000692','000695','000802','000887','000936','000972','001260','002066','002081','002172','002174','002219','002322','002329','002396','002437','002543','002575','002644','002706','002724','002921','300333','300404','300534','300862','300937','301060','688137','688265']))]
print(f'\n8/13 akshare独有股 在 zt_events 中实际存在: {len(ak_only_in_zt)}')
print(ak_only_in_zt.to_string(index=False))

# 真正漏掉的只有 688137 和 688265（不在 stock_pool）
print(f'\n真正漏掉的（不在stock_pool）: 688137, 688265')
print(f'→ 这2只是科创板股票，可能 stock_pool 生成时没有包含')
