"""
扩票池：从21只手挑上游票 → 全A股有色/钢铁/煤炭上游板块（约150只）
用 Baostock 行业分类筛选资源类，下载长历史，做右侧埋伏信号全量扫描验证alpha是否普适
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import baostock as bs
import pandas as pd
from datetime import datetime
from config import DAILY_DIR

# 资源/材料类行业代码（证监会行业分类）
RESOURCE_INDUSTRIES = [
    'C32有色金属冶炼和压延加工业',
    'B09有色金属矿采选业',
    'C31黑色金属冶炼和压延加工业',
    'B06煤炭开采和洗选业',
    'C33金属制品业',
    'B08黑色金属矿采选业',
    'B07石油和天然气开采业',
    'C25石油加工、炼焦和核燃料加工业',
]

START = '2023-07-01'
END = datetime.now().strftime('%Y-%m-%d')

def get_resource_stocks():
    """从行业分类筛选资源类股票，返回 [(code, name, industry)]"""
    rs = bs.query_stock_industry()
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    result = []
    for r in rows:
        update_date, code, name, industry, cls = r
        if industry in RESOURCE_INDUSTRIES:
            # code 格式 sh.600000 / sz.000001
            code6 = code.split('.')[1]
            result.append((code6, name, industry))
    return result

def download_one(bs_code, code):
    rs = bs.query_history_k_data_plus(
        bs_code, "date,open,high,low,close,volume,amount",
        start_date=START, end_date=END, frequency="d"
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=rs.fields)
    for col in ['open','high','low','close','volume','amount']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['date'] = pd.to_datetime(df['date'])
    df['code'] = code
    df = df.dropna(subset=['close'])
    df['pre_close'] = df['close'].shift(1)
    df['turnover'] = 0.0
    return df

def main():
    lg = bs.login()
    if lg.error_code != '0':
        print('[X] 登录失败')
        return
    print('[OK] 登录成功')

    stocks = get_resource_stocks()
    print(f'[OK] 筛选出 {len(stocks)} 只资源类股票')

    # 按行业统计
    from collections import Counter
    ind = Counter([s[2] for s in stocks])
    print('\n行业分布：')
    for k, v in ind.most_common():
        print(f'  {k}: {v}')

    ok = 0
    fail = 0
    for code, name, industry in stocks:
        bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
        try:
            df = download_one(bs_code, code)
            if df is not None and len(df) > 200:
                df.to_csv(os.path.join(DAILY_DIR, code + '.csv'), index=False, encoding='utf-8-sig')
                ok += 1
            else:
                fail += 1
                print(f'[X] {code} {name}: 数据不足({len(df) if df is not None else 0}天)')
        except Exception as e:
            fail += 1
            print(f'[X] {code} {name}: {e}')

    print(f'\n完成: 成功{ok} 失败{fail}')
    bs.logout()

if __name__ == '__main__':
    main()
