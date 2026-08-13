"""
全量扫描：21只上游票3年内所有"埋伏信号"触发点及其后续收益分布
目的：判断埋伏策略的alpha是"可复制规律"还是"2笔主升浪运气"
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from config import DAILY_DIR
from src.sentiment.supply_chain import get_all_upstream_stocks
from src.sentiment.lurk_detector import LurkDetector

detector = LurkDetector()
upstream = get_all_upstream_stocks(("60", "00"))

all_signals = []

for s in upstream:
    code = s["code"]
    path = os.path.join(DAILY_DIR, code + ".csv")
    if not os.path.exists(path):
        continue
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    # 从第120天开始逐日检测（滚动，模拟真实时点）
    for i in range(120, len(df)):
        df_up_to = df.iloc[:i+1]
        r = detector.detect_low_position(code, s["name"], df_up_to)
        if r["eligible"] and r["buy_mode"] != "none":
            # 记录信号，并计算未来收益（未来5/20/60日）
            entry = df['close'].iloc[i]
            fwd = {}
            for horizon, days in [("5d", 5), ("20d", 20), ("60d", 60)]:
                if i + days < len(df):
                    fwd[horizon] = (df['close'].iloc[i+days] / entry - 1) * 100
                else:
                    fwd[horizon] = np.nan
            # 未来最大涨幅（持有期内）
            if i + 60 < len(df):
                fwd_high = df['high'].iloc[i:i+60].max()
                fwd["60d_max"] = (fwd_high / entry - 1) * 100
            all_signals.append({
                'code': code, 'name': s["name"], 'date': df['date'].iloc[i],
                'score': r['score'], 'buy_mode': r['buy_mode'],
                'chg60': r['chg60'], 'vol_ratio': r['vol_ratio'],
                **fwd
            })

sig_df = pd.DataFrame(all_signals)
print(f"=== 3年全量扫描：共 {len(sig_df)} 次埋伏信号 ===\n")

if len(sig_df) > 0:
    print("信号时间分布：")
    sig_df['year_month'] = sig_df['date'].dt.to_period('M')
    print(sig_df.groupby('year_month').size())
    print()

    print("后续收益分布（关键：埋伏后到底涨不涨）：")
    for col in ['5d', '20d', '60d']:
        v = sig_df[col].dropna()
        print(f"  {col}: 均值{v.mean():+.1f}% 中位{v.median():+.1f}% 胜率{(v>0).mean()*100:.0f}% 样本{len(v)}")
    v = sig_df['60d_max'].dropna()
    print(f"  60d_max(持有60日最大涨幅): 均值{v.mean():+.1f}% 中位{v.median():+.1f}%")
    print()

    print("按买入方式分组：")
    for mode in sig_df['buy_mode'].unique():
        sub = sig_df[sig_df['buy_mode'] == mode]
        v20 = sub['20d'].dropna()
        v60 = sub['60d'].dropna()
        print(f"  [{mode}] 样本{len(sub)} | 20日均{v20.mean():+.1f}% 胜率{(v20>0).mean()*100:.0f}% | 60日均{v60.mean():+.1f}%")
    print()

    print("信号明细（按日期）：")
    for _, r in sig_df.iterrows():
        print(f"  {r['date'].strftime('%Y-%m-%d')} {r['code']} {r['name']:8s} {r['buy_mode']:5s} 评分{r['score']} | 60日{r['chg60']:+.1%} 量比{r['vol_ratio']} | 5日{r['5d']:+.1f}% 20日{r['20d']:+.1f}% 60日{r['60d']:+.1f}%")
