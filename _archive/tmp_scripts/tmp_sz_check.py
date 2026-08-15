# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import akshare as ak
import pandas as pd
import baostock as bs

# 拿 08-13 深主板涨停名单
df = ak.stock_zt_pool_em(date='20260813')
codes = df['代码'].astype(str).str.zfill(6)
sz_main = codes[codes.str.startswith(('000','001','002','003'))].tolist()
print('08-13 深主板涨停', len(sz_main), '只:', sz_main[:10])

# 抽查前5只的 baostock 08-11~08-14 数据
bs.login()
for c in sz_main[:5]:
    bc = f"sz.{c}" if c.startswith(('0','3')) else f"sh.{c}"
    rs = bs.query_history_k_data_plus(bc, 'date,close', start_date='2026-08-11', end_date='2026-08-14', frequency='d')
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())
    print(c, rows)
bs.logout()
