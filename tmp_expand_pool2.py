"""
分批下载资源类股票长历史，避免沙箱OOM
每批20只，批间重新login/logout + gc，强制释放内存
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import baostock as bs
import pandas as pd
import gc
from datetime import datetime
from config import DAILY_DIR

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
BATCH = 20

def get_resource_codes():
    """只返回 code 列表，不保留全部rows"""
    rs = bs.query_stock_industry()
    codes = []
    while rs.next():
        update_date, code, name, industry, cls = rs.get_row_data()
        if industry in RESOURCE_INDUSTRIES:
            code6 = code.split('.')[1]
            codes.append(code6)
    return codes

def download_batch(codes):
    """下载一批，返回成功数"""
    ok = 0
    for code in codes:
        bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,open,high,low,close,volume,amount",
                start_date=START, end_date=END, frequency="d"
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=rs.fields)
            for col in ['open','high','low','close','volume','amount']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['date'] = pd.to_datetime(df['date'])
            df['code'] = code
            df = df.dropna(subset=['close'])
            df['pre_close'] = df['close'].shift(1)
            df['turnover'] = 0.0
            if len(df) > 200:
                df.to_csv(os.path.join(DAILY_DIR, code + '.csv'), index=False, encoding='utf-8-sig')
                ok += 1
            del df, rows
        except Exception as e:
            print(f'[X] {code}: {e}')
        gc.collect()
    return ok

def main():
    lg = bs.login()
    if lg.error_code != '0':
        print('[X] 登录失败')
        return
    codes = get_resource_codes()
    bs.logout()
    print(f'[OK] 资源类股票共 {len(codes)} 只')

    total_ok = 0
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i+BATCH]
        lg = bs.login()
        if lg.error_code != '0':
            print(f'[X] 第{i//BATCH+1}批登录失败，跳过')
            continue
        n = download_batch(batch)
        bs.logout()
        total_ok += n
        gc.collect()
        print(f'[OK] 第{i//BATCH+1}批完成: {n}/{len(batch)}，累计{total_ok}')

    print(f'\n全部完成: 成功{total_ok}/{len(codes)}')

if __name__ == '__main__':
    main()
