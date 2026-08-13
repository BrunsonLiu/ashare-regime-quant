import sys
sys.stdout.reconfigure(encoding='utf-8')
import akshare as ak

print("Testing AKShare sentiment APIs...")
try:
    df = ak.stock_zt_pool_em(date='20260731')
    print(f'[OK] zt 20260731: shape={df.shape}, cols={list(df.columns)}')
    if len(df) > 0:
        print(df.head(2).to_string())
except Exception as e:
    print(f'[ERR] zt: {e}')

try:
    df2 = ak.stock_zt_pool_strong_em(date='20260731')
    print(f'[OK] strong_zt 20260731: shape={df2.shape}, cols={list(df2.columns)}')
    if len(df2) > 0:
        print(df2.head(2).to_string())
except Exception as e:
    print(f'[ERR] strong_zt: {e}')

try:
    df3 = ak.stock_zt_pool_zbgc_em(date='20260731')
    print(f'[OK] zt_zbgc 20260731: shape={df3.shape}, cols={list(df3.columns)}')
    if len(df3) > 0:
        print(df3.head(2).to_string())
except Exception as e:
    print(f'[ERR] zbgc: {e}')
