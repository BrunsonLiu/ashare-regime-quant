# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import akshare as ak
import pandas as pd

# 对照：akshare 全市场真实涨停 vs zt_events 记录，看哪些天深市缺失
z = pd.read_csv('data/zt_events.csv', header=None, dtype={1: str}, names=['date','code','lb'])

def board(c):
    if c.startswith('60'): return '沪主板'
    if c.startswith(('000','001','002','003')): return '深主板'
    if c.startswith(('300','301')): return '创业板'
    if c.startswith(('688','689')): return '科创板'
    return '其他'

z['b'] = z['code'].apply(board)

for dt in ['20260811', '20260812', '20260813']:
    akdf = ak.stock_zt_pool_em(date=dt)
    akc = akdf['代码'].astype(str).str.zfill(6)
    ak_b = akc.apply(board)
    real = ak_b.value_counts()
    rec = z[z['date'] == dt.replace('2026','2026-')[:0] + '-'.join([dt[:4],dt[4:6],dt[6:]])]['b'].value_counts()
    d = '-'.join([dt[:4], dt[4:6], dt[6:]])
    rec = z[z['date'] == d]['b'].value_counts()
    print(f'=== {d} 实际涨停(akshare) {len(akdf)}只 vs zt_events记录 {z["date"].eq(d).sum()}只 ===')
    for b in ['沪主板','深主板','创业板','科创板']:
        r = real.get(b, 0); c = rec.get(b, 0)
        flag = '  <<< 缺失' if r > c + 3 else ''
        print(f'  {b}: 实际{r} vs 记录{c}{flag}')
    print()
