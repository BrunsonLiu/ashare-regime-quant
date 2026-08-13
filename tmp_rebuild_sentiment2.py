"""
重建3年全市场情绪序列 v3 — 每只票立即flush，强断点续传
关键改进：
1. 每只票处理后立即 flush（OOM时最多丢1-2只，done与events强一致）
2. 每300只重连一次，防连接老化
3. 只下载 date,high,low,close 三字段，减少内存
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.stdout.reconfigure(encoding='utf-8')

import baostock as bs
import pandas as pd
import gc
from datetime import datetime

START = '2023-07-01'
END = datetime.now().strftime('%Y-%m-%d')

ZT_FILE = 'data/zt_events.csv'
ZHABAN_FILE = 'data/zhaban_events.csv'
DONE_FILE = 'data/zt_done.txt'
LOG_FILE = 'data/zt_rebuild.log'

def get_pool_codes():
    df = pd.read_csv('data/stock_pool.csv')
    return [str(int(c)).zfill(6) for c in df['code']]

def get_limit_pct(code6):
    if code6.startswith('30') or code6.startswith('68'):
        return 0.198
    return 0.098

def load_done():
    if os.path.exists(DONE_FILE):
        with open(DONE_FILE, encoding='utf-8') as f:
            return set(x.strip() for x in f if x.strip())
    return set()

def log(msg):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def main():
    codes = get_pool_codes()
    done = load_done()
    todo = [c for c in codes if c not in done]
    log(f'[START] total={len(codes)} done={len(done)} todo={len(todo)}')
    print(f'[OK] 池子 {len(codes)}，已完成 {len(done)}，待处理 {len(todo)}')

    zt_out = open(ZT_FILE, 'a', encoding='utf-8')
    zb_out = open(ZHABAN_FILE, 'a', encoding='utf-8')
    done_out = open(DONE_FILE, 'a', encoding='utf-8')

    lg = bs.login()
    if lg.error_code != '0':
        print('[X] 登录失败'); return

    processed = 0
    for idx, code in enumerate(todo):
        limit = get_limit_pct(code)
        bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,high,low,close",
                start_date=START, end_date=END, frequency="d"
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if len(rows) >= 2:
                dates = [r[0] for r in rows]
                highs = [float(r[1]) if r[1] else 0.0 for r in rows]
                closes = [float(r[3]) if r[3] else 0.0 for r in rows]
                lianban = 0
                prev_close = None
                for i in range(len(rows)):
                    c = closes[i]
                    if i == 0:
                        prev_close = c
                        continue
                    pc = prev_close
                    prev_close = c
                    if pc <= 0:
                        continue
                    h = highs[i]
                    pct = c / pc - 1
                    high_pct = h / pc - 1
                    ds = dates[i]
                    if pct >= limit and c >= h * 0.995:
                        lianban += 1
                        zt_out.write(f"{ds},{code},{lianban}\n")
                    else:
                        if high_pct >= limit and pct < limit:
                            zb_out.write(f"{ds},{code}\n")
                        lianban = 0
            del rows, dates, highs, closes
        except Exception:
            pass
        done_out.write(code + '\n')
        # 每只票立即flush，保证OOM时一致
        zt_out.flush(); zb_out.flush(); done_out.flush()
        processed += 1

        if processed % 300 == 0:
            bs.logout(); gc.collect(); bs.login()
            log(f'  {processed}/{len(todo)} done')
        elif processed % 50 == 0:
            log(f'  {processed}/{len(todo)} done')

    zt_out.close(); zb_out.close(); done_out.close()
    bs.logout()
    log(f'[DONE] all {len(todo)} processed')
    print(f'[OK] 全部完成')

if __name__ == '__main__':
    main()
