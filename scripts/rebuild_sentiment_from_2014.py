# -*- coding: utf-8 -*-
"""
补爬 2014-2023 涨停事件(为"只做A主线"的12年验证提供情绪数据)
================================================================
现有 zt_events.csv 覆盖 2023-07起; 本脚本补 2014-01 ~ 2023-06, 写入
data/zt_events_pre2023.csv / zhaban_events_pre2023.csv, 之后与现有合并。

前复权(adjustflag=2)判定涨停, 与 rebuild_worker 同口径。
断点续传: data/zt_done_pre2023.txt

用法: python scripts/rebuild_sentiment_from_2014.py [n_stocks]
"""
import os
import sys
import time

import baostock as bs
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8')

START, END = '2014-01-01', '2023-06-30'
ZT = os.path.join(ROOT, 'data', 'zt_events_pre2023.csv')
ZB = os.path.join(ROOT, 'data', 'zhaban_events_pre2023.csv')
DONE = os.path.join(ROOT, 'data', 'zt_done_pre2023.txt')


def limit_pct(code):
    return 0.198 if code.startswith(('30', '68')) else 0.098


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 99999
    pool = pd.read_csv(os.path.join(ROOT, 'data', 'stock_pool.csv'))
    codes = [str(c).zfill(6) for c in pool['code']][:n]
    done = set()
    if os.path.exists(DONE):
        done = set(x.strip() for x in open(DONE, encoding='utf-8') if x.strip())
    todo = [c for c in codes if c not in done]
    print(f'补爬 2014-2023 涨停事件: {len(todo)}/{len(codes)} 只待处理', flush=True)

    lg = bs.login()
    if lg.error_code != '0':
        print('login fail'); return
    zt_out = open(ZT, 'a', encoding='utf-8', buffering=1)
    zb_out = open(ZB, 'a', encoding='utf-8', buffering=1)
    done_out = open(DONE, 'a', encoding='utf-8', buffering=1)

    ok, t0 = 0, time.time()
    for i, code in enumerate(todo):
        lim = limit_pct(code)
        bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,high,low,close", start_date=START, end_date=END,
                frequency="d", adjustflag="2")
            if rs.error_code != '0':
                raise RuntimeError(rs.error_msg)
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if len(rows) >= 2:
                lianban, prev = 0, None
                for j, r in enumerate(rows):
                    c = float(r[3]) if r[3] else 0.0
                    if j == 0:
                        prev = c; continue
                    pc = prev; prev = c
                    if pc <= 0: continue
                    h = float(r[1]) if r[1] else 0.0
                    pct, hpct = c / pc - 1, h / pc - 1
                    if pct >= lim and c >= h * 0.995:
                        lianban += 1
                        zt_out.write(f"{r[0]},{code},{lianban}\n")
                    else:
                        if hpct >= lim and pct < lim:
                            zb_out.write(f"{r[0]},{code}\n")
                        lianban = 0
            done_out.write(code + '\n')
            ok += 1
        except Exception as e:
            print(f'[FAIL] {code}: {e}', flush=True)
        if (i + 1) % 100 == 0:
            print(f'  {i+1}/{len(todo)} ok={ok} {time.time()-t0:.0f}s', flush=True)

    zt_out.close(); zb_out.close(); done_out.close()
    bs.logout()
    print(f'完成 {ok}/{len(todo)}', flush=True)


if __name__ == '__main__':
    main()
