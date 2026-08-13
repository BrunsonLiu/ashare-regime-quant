# -*- coding: utf-8 -*-
"""最小验证：跑段3 (2026-07-14~08-03) 看 BEAR 空仓 + 熔断是否生效"""
import sys
sys.path.insert(0, r'D:\desktop2\quant_a_share')
import os
os.chdir(r'D:\desktop2\quant_a_share')

from main import run_backtest
# 临时修改 start/end？run_backtest 不支持，直接用完整 backtest 但只打印前60行
import main
print('starting short backtest...')
result = run_backtest()
print('done')
print('stats:', result.get('stats', {}))
eq = result.get('equity_curve')
if eq is not None and len(eq) > 0:
    print(eq[['date','equity','regime','position_pct']].tail(30).to_string(index=False))
