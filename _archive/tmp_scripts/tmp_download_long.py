"""
下载产业链上游标的长历史数据（2.5年，用于中线埋伏回测）
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import baostock as bs
import pandas as pd
from datetime import datetime, timedelta
from config import DAILY_DIR
from src.sentiment.supply_chain import get_all_upstream_stocks

START = '2023-07-01'   # 约3年，足够判断低位和横盘
END = datetime.now().strftime('%Y-%m-%d')

def download_one(bs_code, code, name):
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume,amount",
        start_date=START, end_date=END, frequency="d"
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=rs.fields)
    for col in ['open','high','low','close','volume','amount']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df['date'] = pd.to_datetime(df['date'])
    df['code'] = code
    df = df.dropna(subset=['close'])
    # 补 pre_close（昨收，用于涨跌停判断）
    df['pre_close'] = df['close'].shift(1)
    # 补 turnover（换手率，用成交额/流通市值近似，这里暂用 amount 归一）
    df['turnover'] = 0.0
    return df

def main():
    lg = bs.login()
    if lg.error_code != '0':
        print('[X] 登录失败', lg.error_msg)
        return
    print('[OK] 登录成功')

    upstream = get_all_upstream_stocks(("60", "00"))
    print(f'共 {len(upstream)} 只上游标的')

    ok = 0
    fail = 0
    for s in upstream:
        code = s['code']
        bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
        try:
            df = download_one(bs_code, code, s['name'])
            if df is not None and len(df) > 200:
                df.to_csv(os.path.join(DAILY_DIR, code + '.csv'), index=False, encoding='utf-8-sig')
                ok += 1
                print(f'[OK] {code} {s["name"]}: {len(df)} 天')
            else:
                fail += 1
                print(f'[X] {code} {s["name"]}: 数据不足({len(df) if df is not None else 0}天)')
        except Exception as e:
            fail += 1
            print(f'[X] {code} {s["name"]}: {e}')

    print(f'\n完成: 成功{ok} 失败{fail}')
    bs.logout()

if __name__ == '__main__':
    main()
