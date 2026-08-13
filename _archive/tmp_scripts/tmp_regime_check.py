# -*- coding: utf-8 -*-
"""复现段3期间(2026-07-14~08-03)的指数走势 + market_regime.detect 打分明细"""
import sys
sys.path.insert(0, r'D:\desktop2\quant_a_share')
import baostock as bs
import pandas as pd
from src.utils.market_regime import MarketRegime

lg = bs.login()
print("login:", lg.error_code, lg.error_msg)

rs = bs.query_history_k_data_plus(
    "sh.000001", "date,close,volume",
    start_date='2025-06-01', end_date='2026-08-03',
    frequency="d", adjustflag="3")
print("query:", rs.error_code, rs.error_msg)
rows = []
while (rs.error_code == '0') and rs.next():
    rows.append(rs.get_row_data())
df = pd.DataFrame(rows, columns=['date', 'close', 'volume'])
df['close'] = pd.to_numeric(df['close'])
df['volume'] = pd.to_numeric(df['volume'])
df['date'] = pd.to_datetime(df['date'])
print("index rows:", len(df), " first:", df['date'].iloc[0].date(), " last:", df['date'].iloc[-1].date())

# 段3区间逐日走势
seg3 = df[(df['date'] >= '2026-07-14') & (df['date'] <= '2026-08-03')]
print("\n=== 段3区间 上证指数逐日 ===")
prev = None
for _, r in seg3.iterrows():
    pct = (r['close'] / prev - 1) * 100 if prev else 0
    print(f"{r['date'].date()} close={r['close']:.2f} chg={pct:+.2f}%")
    prev = r['close']

# 段3前后对比
d0713 = df[df['date'] == '2026-07-13']['close'].iloc[0]
d0803 = df[df['date'] == '2026-08-03']['close'].iloc[0]
print(f"\n段3整体: 7/13={d0713:.2f} -> 8/3={d0803:.2f}  {((d0803/d0713-1)*100):+.2f}%")
d0620 = df[df['date'] <= '2026-06-20']['close'].iloc[-1]
print(f"6/20={d0620:.2f} -> 8/3={d0803:.2f}  {((d0803/d0620-1)*100):+.2f}%")
hi = df[df['date'] <= '2026-08-03']['close'].max()
hid = df[df['date'] <= '2026-08-03'].loc[df[df['date'] <= '2026-08-03']['close'].idxmax(), 'date']
print(f"截至8/3 区间高点: {hi:.2f} @ {hid.date()}")

# 复现 detect 打分（回测同款: index_up_to 截至当日）
m = MarketRegime()
print("\n=== detect 打分明细(段3各日) ===")
for d in ['2026-07-14', '2026-07-20', '2026-07-24', '2026-07-30', '2026-08-03']:
    sub = df[df['date'] <= d]
    if len(sub) < 60:
        print(d, "rows<60 skip")
        continue
    r = m.detect(sub)
    print(f"{d} -> {r['regime']}  bull={r['bull_score']} bear={r['bear_score']} "
          f"slow_bull={r['slow_bull_score']} maS={r['ma_short']} maL={r['ma_long']} "
          f"trend={r['trend_strength']}% recent20={r['recent_return']}% vol={r['volatility']}% "
          f"dd120={r['drawdown_from_120high']}% policy={r['policy_bias']}")

bs.logout()
print("done")
