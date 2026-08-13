"""
重建3年全市场情绪序列（涨停家数/连板高度/炸板率）
方案：边下边算，不保留原始df；分批防OOM；连板状态机

产物：data/sentiment_3y.csv  {date, zt_count, zhaban_count, zhaban_rate, lianban_height, lianban_dist, ...}
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import baostock as bs
import pandas as pd
import numpy as np
import gc
from datetime import datetime, timedelta
from collections import defaultdict
from config import DAILY_DIR

START = '2023-07-01'
END = datetime.now().strftime('%Y-%m-%d')
BATCH = 50

# 全局状态：逐日聚合
# date -> {'zt': set(code), 'lianban': {code: n}, 'zhaban': set(code)}
daily_zt = defaultdict(set)
daily_lianban = defaultdict(dict)  # date -> {code: 连板数}
daily_zhaban = defaultdict(set)

# 连板状态机：跨日维护 code -> 连续涨停天数
lianban_state = {}

def get_all_codes():
    rs = bs.query_stock_basic()
    codes = []
    while rs.next():
        row = rs.get_row_data()
        code = row[0]  # sh.600000
        code6 = code.split('.')[1]
        codes.append(code6)
    return codes

def get_limit_pct(code6):
    if code6.startswith('30') or code6.startswith('68'):
        return 0.198
    return 0.098

def process_one(code6):
    """下载一只票3年日线，更新全局涨停状态，不返回df"""
    bs_code = f"sh.{code6}" if code6.startswith('6') else f"sz.{code6}"
    limit = get_limit_pct(code6)
    try:
        rs = bs.query_history_k_data_plus(
            bs_code, "date,open,high,low,close,volume,amount",
            start_date=START, end_date=END, frequency="d"
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if len(rows) < 2:
            return
        df = pd.DataFrame(rows, columns=rs.fields)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['open'] = pd.to_numeric(df['open'], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        df = df.dropna(subset=['close']).sort_values('date').reset_index(drop=True)
        df['pre_close'] = df['close'].shift(1)

        # 逐日判断
        for i in range(1, len(df)):
            d = df['date'].iloc[i]
            ds = d.strftime('%Y-%m-%d')
            close = df['close'].iloc[i]
            high = df['high'].iloc[i]
            pc = df['pre_close'].iloc[i]
            if pd.isna(pc) or pc <= 0:
                continue
            pct = close / pc - 1
            high_pct = high / pc - 1
            if pct >= limit and close >= high * 0.995:
                # 涨停封住
                daily_zt[ds].add(code6)
                # 连板状态机
                prev = lianban_state.get(code6, 0)
                lianban_state[code6] = prev + 1
                daily_lianban[ds][code6] = prev + 1
            elif high_pct >= limit and pct < limit:
                # 炸板（盘中触及但收盘没封住）
                daily_zhaban[ds].add(code6)
                lianban_state[code6] = 0
            else:
                lianban_state[code6] = 0
        del df, rows
    except Exception as e:
        pass
    gc.collect()

def main():
    lg = bs.login()
    if lg.error_code != '0':
        print('[X] 登录失败'); return
    codes = get_all_codes()
    bs.logout()
    print(f'[OK] 全市场 {len(codes)} 只')

    total = len(codes)
    for i in range(0, total, BATCH):
        batch = codes[i:i+BATCH]
        lg = bs.login()
        if lg.error_code != '0':
            print(f'[X] 第{i//BATCH+1}批登录失败')
            continue
        for c in batch:
            process_one(c)
        bs.logout()
        gc.collect()
        done = min(i+BATCH, total)
        print(f'[OK] {done}/{total} 完成，当前日期数 {len(daily_zt)}')

    # 聚合成DataFrame
    all_dates = sorted(set(daily_zt.keys()) | set(daily_zhaban.keys()))
    records = []
    for ds in all_dates:
        zt = len(daily_zt[ds])
        zb = len(daily_zhaban[ds])
        rate = zb / max(zt + zb, 1)
        # 连板高度
        lb = daily_lianban.get(ds, {})
        height = max(lb.values()) if lb else 0
        # 连板分布：2板/3板/4板+ 家数
        lb2 = sum(1 for v in lb.values() if v == 2)
        lb3 = sum(1 for v in lb.values() if v == 3)
        lb4 = sum(1 for v in lb.values() if v >= 4)
        records.append({
            'date': ds, 'zt_count': zt, 'zhaban_count': zb,
            'zhaban_rate': round(rate, 4), 'lianban_height': height,
            'lianban2': lb2, 'lianban3': lb3, 'lianban4p': lb4,
        })

    out = pd.DataFrame(records)
    out.to_csv('data/sentiment_3y.csv', index=False, encoding='utf-8-sig')
    print(f'\n[OK] 情绪序列已保存 data/sentiment_3y.csv：{len(out)} 天')
    print(out.tail(10).to_string())

if __name__ == '__main__':
    main()
