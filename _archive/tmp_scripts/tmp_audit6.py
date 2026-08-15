# -*- coding: utf-8 -*-
"""终极根因：worker 取的数据范围 vs 单独查的数据范围"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import baostock as bs

bs.login()

# worker 用 START='2023-07-01' 拉全量数据，然后逐日遍历
# 如果 000006 在 8/13 确实涨停，但没记录，可能是：
# 1) 数据拉取时断了（timeout/异常被 pass 吞掉）
# 2) lianban 计数重置逻辑有问题
# 3) close >= high * 0.995 的浮点精度问题

code = '000006'
bs_code = f'sz.{code}'
limit = 0.098

# 取 8/10~8/13 的数据，模拟 worker
rs = bs.query_history_k_data_plus(
    bs_code, "date,high,low,close",
    start_date='2026-08-10', end_date='2026-08-13', frequency="d"
)
rows = []
while rs.next():
    rows.append(rs.get_row_data())

print(f'=== {code} 8/10~8/13 数据（模拟worker全量拉取的尾部）===')
for r in rows:
    print(f'  date={r[0]}  high={r[1]}  low={r[2]}  close={r[3]}')

# 模拟 worker
print()
print('=== 模拟 worker ===')
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
    high_pct = h / pc - 1
    if pct >= limit and c >= h * 0.995:
        lianban += 1
        print(f'  {r[0]}: 涨停! lianban={lianban}  pct={pct:.6f}')
    else:
        if high_pct >= limit and pct < limit:
            print(f'  {r[0]}: 炸板!  high_pct={high_pct:.6f}')
        else:
            print(f'  {r[0]}: 普通  pct={pct:.6f}')
        lianban = 0

# 现在取全量（从2023-07-01开始），看8/13附近
print()
print('=== 全量拉取 8/10~8/13 尾部 ===')
rs2 = bs.query_history_k_data_plus(
    bs_code, "date,high,low,close",
    start_date='2023-07-01', end_date='2026-08-13', frequency="d"
)
all_rows = []
while rs2.next():
    all_rows.append(rs.get_row_data())

print(f'全量行数: {len(all_rows)}')
print(f'最后5天:')
for r in all_rows[-5:]:
    print(f'  {r}')

# 模拟 worker 全量
print()
print('=== 全量模拟 worker（最后10天）===')
lianban = 0
prev_close = None
results = []
for i, r in enumerate(all_rows):
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
    high_pct = h / pc - 1
    if pct >= limit and c >= h * 0.995:
        lianban += 1
        results.append((r[0], 'ZT', lianban, pct))
    else:
        if high_pct >= limit and pct < limit:
            results.append((r[0], 'ZB', 0, pct))
        lianban = 0

for date, tag, lb, pct in results[-10:]:
    print(f'  {date}  {tag}  lianban={lb}  pct={pct:.6f}')

bs.logout()
