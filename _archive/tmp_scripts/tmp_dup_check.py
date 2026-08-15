# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

# 1. zt_events 是否有重复 (date+code 同一只同一天多条)
z = pd.read_csv('data/zt_events.csv', header=None, dtype={1: str}, names=['date','code','lb'])
dup = z.duplicated(subset=['date','code']).sum()
print('zt_events 总行:', len(z), '| (date,code)重复行:', dup)

# 2. zt_done.txt 是否有重复 code
done = open('data/zt_done.txt', encoding='utf-8').read().splitlines()
done = [x.strip() for x in done if x.strip()]
print('zt_done 行数:', len(done), '| 去重后:', len(set(done)))

# 3. zhaban_events 重复
zb = pd.read_csv('data/zhaban_events.csv', header=None, dtype={1: str}, names=['date','code'])
print('zhaban 总行:', len(zb), '| 重复:', zb.duplicated().sum())

# 4. 每只股票在 zt_events 里同一天连板数是否只记一次
g = z.groupby(['date','code']).size()
print('同(date,code)出现>1次的组数:', (g > 1).sum())

# 5. 抽一只涨停股看连板序列是否合理
sample = '000936'
d = z[z['code'] == sample].sort_values('date')
print('\n000936 涨停记录(近10条):')
print(d.tail(10).to_string(index=False))
