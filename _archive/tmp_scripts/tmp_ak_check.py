# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import akshare as ak

# 涨停股池（东财）最新日期
try:
    df = ak.stock_zt_pool_em(date='20260814')
    print('08-14 涨停股池:', len(df), '只')
    print(df.head(3).to_string())
except Exception as e:
    print('08-14 涨停数据拉取失败:', repr(e)[:200])

try:
    df2 = ak.stock_zt_pool_em(date='20260813')
    print('08-13 涨停股池:', len(df2), '只')
except Exception as e:
    print('08-13 拉取失败:', repr(e)[:200])
