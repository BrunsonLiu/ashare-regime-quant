# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

# 验证时间错位推断：按 zt_done 顺序，检查"最后涨停日期=08-13"的股票在 done 文件里的位置
done = open('data/zt_done.txt', encoding='utf-8').read().splitlines()
done = [x.strip() for x in done if x.strip()]
pos = {c: i for i, c in enumerate(done)}

z = pd.read_csv('data/zt_events.csv', header=None, dtype={1: str}, names=['date','code','lb'])

# 08-13 有涨停记录的股票，在 done 里的位置
d13 = set(z[z['date'] == '2026-08-13']['code'])
print('08-13 有涨停记录的股票数:', len(d13))
print('这些股票在 done 中的位置(索引):')
idx = sorted(pos[c] for c in d13 if c in pos)
print('  最小索引:', idx[0] if idx else None, ' 最大索引:', idx[-1] if idx else None)
print('  done 总数:', len(done))
print('  => 全部落在第2段(done>=3075)?', all(i >= 3075 for i in idx) if idx else 'N/A')

# 反过来：08-12 有记录但 08-13 没有的深主板股，位置
def board(c):
    if c.startswith('60'): return '沪主板'
    if c.startswith(('000','001','002','003')): return '深主板'
    if c.startswith(('300','301')): return '创业板'
    return '其他'
z['b'] = z['code'].apply(board)

sz = set(z[(z['date'] == '2026-08-12') & (z['b'] == '深主板')]['code'])
sz_idx = sorted(pos[c] for c in sz if c in pos)
print('\n08-12 深主板涨停股在 done 的位置: min', min(sz_idx), 'max', max(sz_idx))
print('  => 深主板全部在 done<3075?', all(i < 3075 for i in sz_idx))
