"""
内层：处理一批股票的涨停/炸板事件，写文件后退出
用法：python rebuild_worker.py code1,code2,code3,...

注意: 拉取前复权数据(adjustflag=2)。不复权数据在除权除息日涨幅失真,
会把真实涨停误判为未涨停/把连板错误清零。
(修改复权口径后, 历史数据需重置 zt_done.txt 全量重跑才与新口径一致)
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import baostock as bs
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

START = '2023-07-01'
END = datetime.now().strftime('%Y-%m-%d')
ZT_FILE = os.path.join(ROOT, 'data', 'zt_events.csv')
ZHABAN_FILE = os.path.join(ROOT, 'data', 'zhaban_events.csv')
DONE_FILE = os.path.join(ROOT, 'data', 'zt_done.txt')
FAIL_FILE = os.path.join(ROOT, 'data', 'zt_fail.txt')

def get_limit_pct(code6):
    if code6.startswith('30') or code6.startswith('68'):
        return 0.198
    return 0.098

def main():
    codes = sys.argv[1].split(',') if len(sys.argv) > 1 else []
    if not codes:
        print('no codes'); return

    lg = bs.login()
    if lg.error_code != '0':
        print(f'login fail: {lg.error_msg}'); sys.exit(1)

    # 行缓冲: 每写一行即落盘, 被调度器超时强杀时不丢已抓到的事件
    zt_out = open(ZT_FILE, 'a', encoding='utf-8', buffering=1)
    zb_out = open(ZHABAN_FILE, 'a', encoding='utf-8', buffering=1)
    done_out = open(DONE_FILE, 'a', encoding='utf-8', buffering=1)
    fail_out = open(FAIL_FILE, 'a', encoding='utf-8', buffering=1)

    ok_cnt = 0
    for code in codes:
        limit = get_limit_pct(code)
        bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,high,low,close",
                start_date=START, end_date=END, frequency="d",
                adjustflag="2"  # 前复权
            )
            if rs.error_code != '0':
                raise RuntimeError(f"baostock {rs.error_code}: {rs.error_msg}")
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if len(rows) >= 2:
                lianban = 0
                prev_close = None
                for i in range(len(rows)):
                    r = rows[i]
                    c = float(r[3]) if r[3] else 0.0
                    if i == 0:
                        prev_close = c; continue
                    pc = prev_close; prev_close = c
                    if pc <= 0: continue
                    h = float(r[1]) if r[1] else 0.0
                    pct = c / pc - 1
                    high_pct = h / pc - 1
                    ds = r[0]
                    if pct >= limit and c >= h * 0.995:
                        lianban += 1
                        zt_out.write(f"{ds},{code},{lianban}\n")
                    else:
                        if high_pct >= limit and pct < limit:
                            zb_out.write(f"{ds},{code}\n")
                        lianban = 0
            ok_cnt += 1
            done_out.write(code + '\n')  # 只有成功才标记完成, 失败的下次重试
        except Exception as e:
            print(f'[FAIL] {code}: {e}')
            fail_out.write(f"{code}: {e}\n")
            # 不写 done —— 失败股票留在待办里, 由调度器重试

    zt_out.close(); zb_out.close(); done_out.close(); fail_out.close()
    bs.logout()
    print(f'done {ok_cnt}/{len(codes)}')

if __name__ == '__main__':
    main()
