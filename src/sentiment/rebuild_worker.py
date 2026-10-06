"""
内层：处理一批股票的涨停/炸板事件，写文件后退出
用法：
  python rebuild_worker.py code1,code2,...            # 全量模式(2023-07-01起, 断点续传)
  python rebuild_worker.py code1,code2,... --update   # 增量模式(从状态文件续抓)

数据口径: 前复权(adjustflag=2)。不复权数据在除权除息日涨幅失真,
会把真实涨停误判为未涨停/把连板错误清零。

增量连续性: 状态文件记录每只股票 (最后抓取日, 连板计数断点),
增量窗口以最后抓取日为种子行(只作昨收/连板初值, 不重复写事件),
跨边界的连板序列严格延续。
"""
import sys, os, csv
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
STATE_FILE = os.path.join(ROOT, 'data', 'zt_state.csv')

def get_limit_pct(code6):
    if code6.startswith('30') or code6.startswith('68'):
        return 0.198
    return 0.098

def load_state():
    """{code: (last_date, lianban_end)} —— 增量续抓的断点"""
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding='utf-8') as f:
                for row in csv.reader(f):
                    if len(row) >= 3 and row[0].strip():
                        state[row[0].strip()] = (row[1].strip(), int(float(row[2])))
        except Exception as e:
            print(f'[WARN] 状态文件读取失败, 按全量处理: {e}')
    return state

def main():
    args = [a for a in sys.argv[1:] if a != '--update']
    update_mode = '--update' in sys.argv
    codes = args[0].split(',') if args else []
    if not codes:
        print('no codes'); return

    lg = bs.login()
    if lg.error_code != '0':
        print(f'login fail: {lg.error_msg}'); sys.exit(1)

    state = load_state() if update_mode else {}

    # 行缓冲: 每写一行即落盘, 被调度器超时强杀时不丢已抓到的事件
    zt_out = open(ZT_FILE, 'a', encoding='utf-8', buffering=1)
    zb_out = open(ZHABAN_FILE, 'a', encoding='utf-8', buffering=1)
    done_out = open(DONE_FILE, 'a', encoding='utf-8', buffering=1)
    fail_out = open(FAIL_FILE, 'a', encoding='utf-8', buffering=1)
    state_out = open(STATE_FILE, 'a', encoding='utf-8', buffering=1)

    ok_cnt = 0
    for code in codes:
        limit = get_limit_pct(code)
        bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"

        # 增量模式: 从状态断点续抓; 种子行(最后抓取日)只提供昨收与连板初值
        if update_mode and code in state:
            start, init_lianban = state[code]
        else:
            start, init_lianban = START, 0

        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,high,low,close",
                start_date=start, end_date=END, frequency="d",
                adjustflag="2"  # 前复权
            )
            if rs.error_code != '0':
                raise RuntimeError(f"baostock {rs.error_code}: {rs.error_msg}")
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if rows:
                lianban = init_lianban
                for i, r in enumerate(rows):
                    c = float(r[3]) if r[3] else 0.0
                    if i == 0:
                        prev_close = c
                        continue
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
                state_out.write(f"{code},{rows[-1][0]},{lianban}\n")
            else:
                # 无数据(长期停牌/新代码): 状态原样续写, 避免每次重试
                if code in state:
                    ld, lb = state[code]
                    state_out.write(f"{code},{ld},{lb}\n")
            ok_cnt += 1
            if not update_mode:
                done_out.write(code + '\n')  # 全量模式才推进 done 断点
        except Exception as e:
            print(f'[FAIL] {code}: {e}')
            fail_out.write(f"{code}: {e}\n")
            # 不写 done/state —— 失败股票留在待办里, 由调度器重试

    zt_out.close(); zb_out.close(); done_out.close(); fail_out.close(); state_out.close()
    bs.logout()
    mode = 'update' if update_mode else 'full'
    print(f'done[{mode}] {ok_cnt}/{len(codes)}')

if __name__ == '__main__':
    main()
