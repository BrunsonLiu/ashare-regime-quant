# -*- coding: utf-8 -*-
"""深挖 8/13 涨停差异：akshare 59 vs baostock 28"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import baostock as bs

zt = pd.read_csv('data/zt_events.csv', names=['date','code','lianban'])
zt_0813 = zt[zt['date'] == '2026-08-13']
bs_codes = set(zt_0813['code'].astype(str).str.zfill(6).tolist())

import akshare as ak
ak_zt = ak.stock_zt_pool_em(date='20260813')
ak_codes = set(ak_zt['代码'].astype(str).tolist())

# akshare 有但 baostock 没有的 32 只
ak_only = ak_codes - bs_codes
print(f'akshare有但baostock没有: {len(ak_only)} 只')
print(sorted(ak_only))
print()

# 逐个查 baostock 原始日线
bs.login()
print('=== 逐个查 akshare独有 的日线数据 ===')
for code in sorted(ak_only):
    bs_code = f'sh.{code}' if code.startswith('6') else f'sz.{code}'
    limit = 0.198 if code.startswith('30') or code.startswith('68') else 0.098
    rs = bs.query_history_k_data_plus(
        bs_code, "date,open,high,low,close,preclose",
        start_date='2026-08-12', end_date='2026-08-13', frequency="d"
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        print(f'  {code} ({bs_code}): 无数据')
        continue
    r = rows[-1]  # 8/13
    if len(rows) < 2:
        print(f'  {code}: 只有1天数据 {rows[0]}')
        continue
    r_prev = rows[-2]
    close = float(r[4]) if r[4] else 0
    preclose = float(r[5]) if r[5] else 0
    high = float(r[2]) if r[2] else 0
    pct = close / preclose - 1 if preclose > 0 else 0
    high_pct = high / preclose - 1 if preclose > 0 else 0
    
    # baostock 的判定条件: pct >= limit AND close >= high * 0.995
    zt_judge = pct >= limit and close >= high * 0.995
    reason = []
    if pct < limit:
        reason.append(f'pct={pct:.4f} < limit={limit:.3f}')
    if close < high * 0.995:
        reason.append(f'close={close} < high*0.995={high*0.995:.2f}')
    
    print(f'  {code} ({bs_code}): close={close} high={high} preclose={preclose} pct={pct:.4f} high_pct={high_pct:.4f} limit={limit:.3f} zt={zt_judge} {"; ".join(reason) if reason else ""}')

# baostock 有但 akshare 没有的
bs_only = bs_codes - ak_codes
print()
print(f'baostock有但akshare没有: {len(bs_only)} 只')
for code in sorted(bs_only):
    bs_code = f'sh.{code}' if code.startswith('6') else f'sz.{code}'
    limit = 0.198 if code.startswith('30') or code.startswith('68') else 0.098
    rs = bs.query_history_k_data_plus(
        bs_code, "date,open,high,low,close,preclose",
        start_date='2026-08-12', end_date='2026-08-13', frequency="d"
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if len(rows) >= 2:
        r = rows[-1]
        close = float(r[4]) if r[4] else 0
        preclose = float(r[5]) if r[5] else 0
        high = float(r[2]) if r[2] else 0
        pct = close / preclose - 1 if preclose > 0 else 0
        print(f'  {code} ({bs_code}): close={close} high={high} preclose={preclose} pct={pct:.4f} limit={limit:.3f}')

bs.logout()
