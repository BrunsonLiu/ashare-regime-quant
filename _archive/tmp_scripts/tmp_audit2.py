# -*- coding: utf-8 -*-
"""审计涨停判定逻辑：用 akshare 交叉验证 baostock 的结果"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import akshare as ak

# 1) 取 akshare 涨停板数据（同花顺概念）
print('=== akshare 涨停板行情（最近几个交易日）===')
try:
    ak_zt = ak.stock_zt_pool_em(date='20260813')
    print(f'2026-08-13 akshare涨停数: {len(ak_zt)}')
    print(ak_zt[['代码','名称','涨停统计','连板数']].head(10).to_string(index=False))
except Exception as e:
    print(f'akshare 20260813 失败: {e}')

print()
try:
    ak_zt2 = ak.stock_zt_pool_em(date='20260812')
    print(f'2026-08-12 akshare涨停数: {len(ak_zt2)}')
except Exception as e:
    print(f'akshare 20260812 失败: {e}')

print()
try:
    ak_zt3 = ak.stock_zt_pool_em(date='20260810')
    print(f'2026-08-10 akshare涨停数: {len(ak_zt3)}')
except Exception as e:
    print(f'akshare 20260810 失败: {e}')

# 2) 对比 baostock 结果
print()
print('=== baostock 结果对比 ===')
zt = pd.read_csv('data/zt_events.csv', names=['date','code','lianban'])
for d in ['2026-08-13', '2026-08-12', '2026-08-10']:
    n = len(zt[zt['date'] == d])
    print(f'{d} baostock涨停数: {n}')

# 3) 抽检：从 akshare 涨停池取几个 code，验证 baostock 是否也判定为涨停
print()
print('=== 逐股抽检（2026-08-13）===')
if 'ak_zt' in dir() and len(ak_zt) > 0:
    zt_0813 = zt[zt['date'] == '2026-08-13']
    bs_codes = set(zt_0813['code'].astype(str).str.zfill(6).tolist())
    ak_codes = set(ak_zt['代码'].astype(str).tolist())
    
    print(f'akshare涨停codes: {len(ak_codes)}')
    print(f'baostock涨停codes: {len(bs_codes)}')
    print(f'交集: {len(ak_codes & bs_codes)}')
    print(f'akshare有但baostock没有: {len(ak_codes - bs_codes)}')
    print(f'baostock有但akshare没有: {len(bs_codes - ak_codes)}')
    
    if ak_codes - bs_codes:
        diff1 = list(ak_codes - bs_codes)[:10]
        print(f'  akshare独有(前10): {diff1}')
    if bs_codes - ak_codes:
        diff2 = list(bs_codes - ak_codes)[:10]
        print(f'  baostock独有(前10): {diff2}')

# 4) 检查 2023 年数据起始是否正确
print()
print('=== 2023年7月初数据检查 ===')
early = zt[zt['date'] < '2023-07-10'].sort_values(['date','code'])
print(f'2023-07-04 ~ 2023-07-09 涨停事件: {len(early)}')
print(early.head(15).to_string(index=False))

# 5) 检查 baostock 涨停判定阈值是否正确
# 60/68 开头应该用 19.8%，其他用 9.8%
print()
print('=== 涨停阈值检查 ===')
# 取几个已知的涨停，回看原始日线数据验证
import baostock as bs
bs.login()

test_codes = ['000001', '600000', '300001', '688001']
for code in test_codes:
    bs_code = f'sh.{code}' if code.startswith('6') else f'sz.{code}'
    rs = bs.query_history_k_data_plus(
        bs_code, "date,high,low,close,preclose",
        start_date='2026-08-10', end_date='2026-08-13', frequency="d"
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if rows:
        print(f'{code} ({bs_code}):')
        for r in rows:
            close = float(r[3]) if r[3] else 0
            preclose = float(r[4]) if r[4] else 0
            pct = (close/preclose - 1) * 100 if preclose > 0 else 0
            print(f'  {r[0]}  close={close}  preclose={preclose}  pct={pct:.2f}%')

bs.logout()
