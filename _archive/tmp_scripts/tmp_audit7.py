# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import baostock as bs

bs.login()

# 只取 000006 在 2026-07-01 ~ 2026-08-13 的数据
code = '000006'
bs_code = 'sz.000006'
limit = 0.098

rs = bs.query_history_k_data_plus(
    bs_code, "date,high,low,close",
    start_date='2026-07-01', end_date='2026-08-13', frequency="d"
)
rows = []
while rs.next():
    rows.append(rs.get_row_data())

print(f'000006  2026-07-01~08-13  共{len(rows)}天')

# 模拟 worker
lianban = 0
prev_close = None
for i, r in enumerate(rows):
    c = float(r[3]) if r[3] else 0.0
    if i == 0:
        prev_close = c
        continue
    pc = prev_close
    prev_close = c
    if pc <= 0:
        continue
    h = float(r[1]) if r[1] else 0.0
    pct = c / pc - 1
    if pct >= limit and c >= h * 0.995:
        lianban += 1
        print(f'  {r[0]}: ZT lianban={lianban} pct={pct:.6f}')
    else:
        high_pct = h / pc - 1
        if high_pct >= limit and pct < limit:
            print(f'  {r[0]}: ZB high_pct={high_pct:.6f}')
        lianban = 0

# 再查 000593
print()
code2 = '000593'
rs2 = bs.query_history_k_data_plus(
    'sz.000593', "date,high,low,close",
    start_date='2026-08-10', end_date='2026-08-13', frequency="d"
)
rows2 = []
while rs2.next():
    rows2.append(rs.get_row_data())

print(f'000593  8/10~8/13  共{len(rows2)}天')
lianban = 0
prev_close = None
for i, r in enumerate(rows2):
    c = float(r[3]) if r[3] else 0.0
    if i == 0:
        prev_close = c
        continue
    pc = prev_close
    prev_close = c
    if pc <= 0:
        continue
    h = float(r[1]) if r[1] else 0.0
    pct = c / pc - 1
    if pct >= limit and c >= h * 0.995:
        lianban += 1
        print(f'  {r[0]}: ZT lianban={lianban} pct={pct:.6f}')
    else:
        lianban = 0
        print(f'  {r[0]}: normal pct={pct:.6f}')

bs.logout()
