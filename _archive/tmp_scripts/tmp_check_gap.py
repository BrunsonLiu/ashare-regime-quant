# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

p = pd.read_csv('data/stock_pool.csv')
print('列:', list(p.columns))
print('总行数:', len(p))
print('code dtype:', p['code'].dtype)
print('前30行 code 原始值:')
print(p['code'].head(30).tolist())
print('name 样例:', p['name'].head(10).tolist())
