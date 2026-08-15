# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import baostock as bs

lg = bs.login()
print('login', lg.error_code)
for code in ['000001', '600000', '000936']:
    bs_code = f"sz.{code}" if code.startswith(('0', '3')) else f"sh.{code}"
    rs = bs.query_history_k_data_plus(bs_code, 'date,close', start_date='2026-08-11', end_date='2026-08-14', frequency='d')
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())
    print(code, '近4日:', rows)
bs.logout()
