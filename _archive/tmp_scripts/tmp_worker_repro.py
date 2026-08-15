# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import baostock as bs

# 用 rebuild_worker 完全相同的逻辑，看 000802 在 08-13 是否被记为涨停
bs.login()
c = '000802'
bc = f"sz.{c}"
rs = bs.query_history_k_data_plus(bc, "date,high,low,close", start_date='2026-08-11', end_date='2026-08-13', frequency="d")
rows = []
while rs.error_code == '0' and rs.next():
    rows.append(rs.get_row_data())
bs.logout()

print('000802 数据:')
for r in rows:
    print(r)

print('\n按 worker 逻辑判断 (limit=0.098):')
prev_close = None
for r in rows:
    c0 = float(r[3])
    if prev_close is None:
        prev_close = c0
        continue
    pc = prev_close; prev_close = c0
    h = float(r[1])
    pct = c0 / pc - 1
    high_pct = h / pc - 1
    flag = '涨停' if (pct >= 0.098 and c0 >= h * 0.995) else ('炸板' if (high_pct >= 0.098 and pct < 0.098) else '')
    print(f'{r[0]}: close={c0} pct={pct:.4f} high_pct={high_pct:.4f} -> {flag}')
