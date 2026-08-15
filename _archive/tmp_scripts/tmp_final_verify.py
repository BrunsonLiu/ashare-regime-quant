# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

z = pd.read_csv('data/zt_events.csv', header=None, dtype={1: str}, names=['date','code','lb'])

# 关键验证：深主板股票，它们在 zt_events 里"最后一条记录"是不是都停在 08-12 或更早？
def board(c):
    if c.startswith('60'): return '沪主板'
    if c.startswith(('000','001','002','003')): return '深主板'
    if c.startswith(('300','301')): return '创业板'
    return '其他'

z['b'] = z['code'].apply(board)
sz = z[z['b'] == '深主板']
last_sz = sz.groupby('code')['date'].max()
print('=== 深主板股票 最后涨停记录日期分布(尾部10天) ===')
print(last_sz.value_counts().sort_index().tail(10).to_string())
print('深主板最后记录=08-13的股票数:', (last_sz == '2026-08-13').sum())
print('深主板最后记录=08-12的股票数:', (last_sz == '2026-08-12').sum())

# 这些 08-12 涨停的深主板股，08-13 是否其实是涨停(akshare显示24只)但没被记录？
sz_0812 = set(sz[sz['date'] == '2026-08-12']['code'])
print('\n08-12 深主板涨停股数:', len(sz_0812))

# 结论: 深主板在 08-13 的记录为0，说明重建时这些股票的数据只更新到 08-12
# 检查 baostock 是否 08-13 深市数据当时未发布（时间错位）
import baostock as bs
bs.login()
# 深主板 08-13 涨停股 002329 的重建窗口
rs = bs.query_history_k_data_plus('sz.002329', 'date,close', start_date='2026-08-12', end_date='2026-08-13', frequency='d')
rows = []
while rs.error_code == '0' and rs.next():
    rows.append(rs.get_row_data())
print('\n002329 08-12~13 baostock:', rows)
bs.logout()
