# -*- coding: utf-8 -*-
"""根因分析：为什么 32 只确认涨停但 rebuild_worker 没记录"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import baostock as bs

zt = pd.read_csv('data/zt_events.csv', names=['date','code','lianban'])

# 取 8/13 漏掉的 000006 为例
# rebuild_worker 的逻辑：用 query_history_k_data_plus 取 date,high,low,close
# 然后用前一天 close 作为 preclose，而不是用 baostock 的 preclose 字段
# 关键：worker 取的字段是 "date,high,low,close" — 没有 preclose
# 它用前一天的 close 作为 prev_close

code = '000006'
bs_code = f'sz.{code}'
limit = 0.098

bs.login()
rs = bs.query_history_k_data_plus(
    bs_code, "date,high,low,close",
    start_date='2026-08-10', end_date='2026-08-13', frequency="d"
)
rows = []
while rs.next():
    rows.append(rs.get_row_data())

print(f'=== {code} 日线 (worker 使用的字段: date,high,low,close) ===')
for r in rows:
    print(f'  {r[0]}  high={r[1]}  low={r[2]}  close={r[3]}')

# 模拟 worker 逻辑
print()
print('=== 模拟 worker 逻辑 ===')
lianban = 0
prev_close = None
for i, r in enumerate(rows):
    c = float(r[3]) if r[3] else 0.0
    if i == 0:
        prev_close = c
        print(f'  {r[0]}: 初始化 prev_close={prev_close}')
        continue
    pc = prev_close
    prev_close = c
    if pc <= 0:
        continue
    h = float(r[1]) if r[1] else 0.0
    pct = c / pc - 1
    high_pct = h / pc - 1
    zt_judge = pct >= limit and c >= h * 0.995
    print(f'  {r[0]}: close={c} prev_close={pc} pct={pct:.6f} limit={limit} high={h} high_pct={high_pct:.6f} close>=high*0.995={c>=h*0.995} zt={zt_judge}')

# 关键检查：close >= high * 0.995 这个条件
# 000006: close=7.7 high=7.7 → 7.7 >= 7.7*0.995=7.6615 → True
# pct = 7.7/7.0 - 1 = 0.1 >= 0.098 → True
# 所以判定应该是 True！那为什么没记录？

# 检查：是不是 000006 根本不在 stock_pool 里？
pool = pd.read_csv('data/stock_pool.csv')
pool_codes = set(str(int(c)).zfill(6) for c in pool['code'])
print()
print(f'000006 在 stock_pool 中: {code in pool_codes}')

# 检查 zt_done 中是否有 000006
done = set(x.strip() for x in open('data/zt_done.txt', encoding='utf-8') if x.strip())
print(f'000006 在 zt_done 中: {code in done}')

# 检查 000006 在 zt_events 中的所有记录
zt_006 = zt[zt['code'].astype(str).str.zfill(6) == code]
print(f'000006 在 zt_events 中记录数: {len(zt_006)}')
if len(zt_006) > 0:
    print(zt_006.to_string(index=False))

# 再查几个漏掉的
print()
print('=== 检查所有32只漏股是否在 stock_pool / zt_done / zt_events 中 ===')
ak_only = ['000006','000593','000692','000695','000802','000887','000936','000972',
           '001260','002066','002081','002172','002174','002219','002322','002329',
           '002396','002437','002543','002575','002644','002706','002724','002921',
           '300333','300404','300534','300862','300937','301060','688137','688265']

in_pool = []
not_in_pool = []
in_done = []
not_in_done = []
in_zt = []
not_in_zt = []

for c in ak_only:
    c6 = c.zfill(6)
    in_pool_flag = c6 in pool_codes
    in_done_flag = c6 in done
    in_zt_flag = len(zt[zt['code'].astype(str).str.zfill(6) == c6]) > 0
    
    if in_pool_flag:
        in_pool.append(c6)
    else:
        not_in_pool.append(c6)
    if in_done_flag:
        in_done.append(c6)
    else:
        not_in_done.append(c6)
    if in_zt_flag:
        in_zt.append(c6)
    else:
        not_in_zt.append(c6)

print(f'在stock_pool中: {len(in_pool)}/{len(ak_only)}')
print(f'不在stock_pool中: {len(not_in_pool)} → {not_in_pool[:10]}')
print(f'在zt_done中: {len(in_done)}/{len(ak_only)}')
print(f'不在zt_done中: {len(not_in_done)} → {not_in_done[:10]}')
print(f'在zt_events中有记录: {len(in_zt)}/{len(ak_only)}')
print(f'在zt_events中无记录: {len(not_in_zt)} → {not_in_zt[:10]}')

bs.logout()
