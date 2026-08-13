import baostock as bs
import sys
sys.stdout.reconfigure(encoding='utf-8')

lg = bs.login()
print('login', lg.error_code)

tests = [
    'date,close',
    'date,open,close',
    'date,open,high,low,close',
    'date,open,high,low,close,volume',
    'date,open,high,low,close,volume,amount',
    'date,open,high,low,close,volume,amount,turnover',
    'date,open,high,low,close,volume,amount,turnover,pctChg',
]

for fields in tests:
    rs = bs.query_history_k_data_plus(
        'sh.601899', fields,
        start_date='2023-07-01', end_date='2026-08-12', frequency='d'
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    print(f'{len(rows):4d} rows | fields={rs.fields}')

bs.logout()
