# -*- coding: utf-8 -*-
import pandas as pd

pool = pd.read_csv('data/stock_pool.csv', encoding='utf-8-sig')
pool['c'] = pool['code'].astype(str).str.zfill(6)
nm = dict(zip(pool['c'], pool['name']))

t = pd.read_csv('data/backtest_trades.csv', dtype={'code': str})
t['code'] = t['code'].str.zfill(6)
t['name'] = t['code'].map(nm)
t['date'] = pd.to_datetime(t['date']).dt.strftime('%m/%d')

sells = t[t['action'] == 'SELL']
buys = t[t['action'] == 'BUY']

total = sells['pnl'].sum()
wins = (sells['pnl'] > 0).sum()
losses = (sells['pnl'] <= 0).sum()
win_pnl = sells[sells['pnl'] > 0]['pnl'].sum()
loss_pnl = sells[sells['pnl'] <= 0]['pnl'].sum()

print("=" * 85)
print(f"{'日期':>6s} | {'代码':>6s} {'名称':<6s} | {'买入日':>5s} @{'买入价':>8s} | {'卖出价':>8s} | {'盈亏':>10s} {'收益率':>8s} | 持 天 | 理由")
print("=" * 85)

for _, sr in sells.iterrows():
    bm = buys[(buys['code'] == sr['code']) & (buys['date'] < sr['date'])]
    if len(bm) > 0:
        bd = bm['date'].iloc[-1]
        bp = bm['price'].iloc[-1]
        dur = (pd.to_datetime('2026-' + sr['date']) - pd.to_datetime('2026-' + bd)).days
    else:
        bd = '?'
        bp = None
        dur = None

    bp_str = f"@{bp:>8.2f}" if bp is not None else '@       ?'
    dur_str = f"{dur:>2d}" if dur is not None else ' ?'
    name_str = sr['name'] if pd.notna(sr['name']) else '???'
    code_s = str(sr['code'])
    price_s = float(sr['price'])
    pnl_s = float(sr['pnl'])
    pnl_pct_s = float(sr['pnl_pct'])
    reason_s = str(sr['reason']) if pd.notna(sr['reason']) else ''
    print(f"{sr['date']:>6s} | {code_s:>6s} {name_str:<6s} | {bd:>5s} {bp_str} | @{price_s:>8.2f} | {pnl_s:>+10.0f} {pnl_pct_s:>+7.1f}% | 持{dur_str}天 | {reason_s}")

print("=" * 85)
print(f"\n总笔数: {len(sells)}  |  盈: {wins}  亏: {losses}  |  胜率: {wins/len(sells)*100:.1f}%")
print(f"盈利合计: +{win_pnl:.0f}  |  亏损合计: {loss_pnl:.0f}")
print(f"总净利: {total:+.0f}  ({(total/100000)*100:+.2f}%)")
print(f"盈亏比: {abs(win_pnl/max(loss_pnl,1)):.2f} : 1")

# 按股票汇总
print("\n=== 按股票汇总 ===")
summary = sells.groupby(['code', 'name']).agg(
    cnt=('pnl', 'count'),
    win_cnt=('pnl', lambda x: (x > 0).sum()),
    total_pnl=('pnl', 'sum'),
    avg_pnl=('pnl', 'mean'),
).sort_values('total_pnl', ascending=False)
for (code, name), row in summary.iterrows():
    wc = int(row['win_cnt'])
    tc = int(row['cnt'])
    name_str = name if pd.notna(name) else '???'
    print(f"  {code} {name_str:<6s}  {tc}笔 盈{wc}/{tc}  累计 {row['total_pnl']:+.0f}  均笔 {row['avg_pnl']:+.0f}")
