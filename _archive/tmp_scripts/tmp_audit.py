# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

zt = pd.read_csv('data/zt_events.csv', names=['date','code','lianban'])
zb = pd.read_csv('data/zhaban_events.csv', names=['date','code'])
s = pd.read_csv('data/sentiment_3y.csv')

print(f'sentiment rows: {len(s)}, range: {s.date.min()} ~ {s.date.max()}')
print()

# 1) zt_count 交叉验证
za = zt.groupby('date').size().reset_index(name='zt_calc')
m = s.merge(za, on='date', how='left')
m['zt_calc'] = m['zt_calc'].fillna(0).astype(int)
diff = m[m['zt_count'] != m['zt_calc']]
print(f'zt_count 不一致天数: {len(diff)}')
if len(diff) > 0:
    print(diff[['date','zt_count','zt_calc']].head(20).to_string(index=False))
print()

# 2) zhaban_count 交叉验证
za2 = zb.groupby('date').size().reset_index(name='zb_calc')
m2 = s.merge(za2, on='date', how='left')
m2['zb_calc'] = m2['zb_calc'].fillna(0).astype(int)
diff2 = m2[m2['zhaban_count'] != m2['zb_calc']]
print(f'zhaban_count 不一致天数: {len(diff2)}')
if len(diff2) > 0:
    print(diff2[['date','zhaban_count','zb_calc']].head(20).to_string(index=False))
print()

# 3) lianban_height 交叉验证
zh = zt.groupby('date')['lianban'].max().reset_index(name='lb_calc')
m3 = s.merge(zh, on='date', how='left')
m3['lb_calc'] = m3['lb_calc'].fillna(0).astype(int)
diff3 = m3[m3['lianban_height'] != m3['lb_calc']]
print(f'lianban_height 不一致天数: {len(diff3)}')
if len(diff3) > 0:
    print(diff3[['date','lianban_height','lb_calc']].head(20).to_string(index=False))
print()

# 4) 检查 zt_events 里的日期是否都在 sentiment_3y 里
zt_dates = set(zt['date'].unique())
s_dates = set(s['date'].unique())
orphan = zt_dates - s_dates
print(f'zt_events 中有但 sentiment_3y 中没有的日期: {len(orphan)}')
if orphan:
    print(sorted(orphan)[:20])
print()

# 5) 检查 sentiment_3y 中 zt_count=0 的天（应该没有涨停事件）
zero_zt = s[s['zt_count'] == 0]
print(f'sentiment_3y 中 zt_count=0 的天数: {len(zero_zt)}')
if len(zero_zt) > 0:
    print(zero_zt[['date','zt_count','zhaban_count','lianban_height']].head(10).to_string(index=False))
print()

# 6) stock_pool vs zt_done 交叉验证
pool = pd.read_csv('data/stock_pool.csv')
pool_codes = set(str(int(c)).zfill(6) for c in pool['code'])
done_codes = set(x.strip() for x in open('data/zt_done.txt', encoding='utf-8') if x.strip())
print(f'stock_pool: {len(pool_codes)} codes, zt_done: {len(done_codes)} codes')
print(f'pool有但done没有: {len(pool_codes - done_codes)}')
print(f'done有但pool没有: {len(done_codes - pool_codes)}')
if pool_codes - done_codes:
    print('缺失codes:', sorted(pool_codes - done_codes)[:20])
print()

# 7) 检查 zt_events 里的 code 是否都在 stock_pool 里
zt_codes = set(zt['code'].astype(str).str.zfill(6).unique())
print(f'zt_events unique codes: {len(zt_codes)}, 其中不在stock_pool的: {len(zt_codes - pool_codes)}')
if zt_codes - pool_codes:
    print('不在pool的codes:', sorted(zt_codes - pool_codes)[:20])
print()

# 8) 连板逻辑抽检：随机取几个连板>=3的，检查前后日期是否连续
import random
random.seed(42)
high_lb = zt[zt['lianban'] >= 3].copy()
sample = high_lb.sample(min(10, len(high_lb)))
print('=== 连板>=3 抽检（检查前N天是否有连板序列）===')
for _, row in sample.iterrows():
    code = str(row['code']).zfill(6)
    date = row['date']
    lb = row['lianban']
    # 取该code该日期前lb天的记录
    sub = zt[(zt['code'] == row['code']) & (zt['date'] <= date)].sort_values('date').tail(lb)
    dates_seq = sub['date'].tolist()
    lbs_seq = sub['lianban'].tolist()
    ok = lbs_seq == list(range(1, lb + 1))
    print(f'  {date} {code} lianban={lb}  seq_dates={dates_seq}  seq_lb={lbs_seq}  valid={ok}')
