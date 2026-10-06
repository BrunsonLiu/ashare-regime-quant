"""
外层调度：读取待处理股票，每30只启动一个全新子进程处理
子进程独立连接、独立内存，处理完退出 → 彻底避免连接老化/内存累积

两种模式:
  python rebuild_scheduler.py            # 全量: 处理 done 文件之外的代码(断点续传)
  python rebuild_scheduler.py --update   # 增量: 处理状态文件中 last_date 落后于
                                         # 最近交易日的代码(日常更新, 分钟级)
断点续传：全量模式看 zt_done.txt; 增量模式看 zt_state.csv (code,last_date,lianban_end)
失败重试: 同批无进展重试至多 MAX_ATTEMPTS 次, 防止确定性失败死循环
"""
import sys, os, subprocess, time, csv
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import baostock as bs

# 项目根目录（本文件位于 src/sentiment/ 下，向上两级）
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rebuild_worker.py')

BATCH = 30
MAX_ATTEMPTS = 2        # 同一批最多重试次数，防止确定性失败导致死循环
TIMEOUT = 900           # 30只 × 每只数秒 + 登录，120s 必超时强杀
DONE_FILE = os.path.join(ROOT, 'data', 'zt_done.txt')
STATE_FILE = os.path.join(ROOT, 'data', 'zt_state.csv')
LOG_FILE = os.path.join(ROOT, 'data', 'zt_rebuild.log')
POOL_FILE = os.path.join(ROOT, 'data', 'stock_pool.csv')

def get_pool_codes():
    df = pd.read_csv(POOL_FILE)
    return [str(int(c)).zfill(6) for c in df['code']]

def load_done():
    if os.path.exists(DONE_FILE):
        with open(DONE_FILE, encoding='utf-8') as f:
            return set(x.strip() for x in f if x.strip())
    return set()

def load_state():
    """{code: last_date}"""
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding='utf-8') as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0].strip():
                    state[row[0].strip()] = row[1].strip()
    return state

def last_trade_day():
    """最近一个已收盘的交易日(baostock交易日历); 失败则回退今天"""
    today = pd.Timestamp.now().strftime('%Y-%m-%d')
    try:
        lg = bs.login()
        if lg.error_code != '0':
            return today
        rs = bs.query_trade_dates(start_date='2025-01-01', end_date=today)
        days = []
        while rs.next():
            d = rs.get_row_data()
            if len(d) >= 2 and d[1] == '1':
                days.append(d[0])
        bs.logout()
        return days[-1] if days else today
    except Exception:
        return today

def log(msg):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def compact_state():
    """压实状态文件(同code保留最后一行): 追加式写入的定期整理, 原子替换"""
    if not os.path.exists(STATE_FILE):
        return
    latest = {}
    order = []
    with open(STATE_FILE, encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) >= 3 and row[0].strip():
                c = row[0].strip()
                if c not in latest:
                    order.append(c)
                latest[c] = (row[1].strip(), row[2].strip())
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        for c in order:
            d, lb = latest[c]
            w.writerow([c, d, lb])
    os.replace(tmp, STATE_FILE)

def main():
    update_mode = '--update' in sys.argv

    codes = get_pool_codes()
    if update_mode:
        ref = last_trade_day()
        state = load_state()
        todo = [c for c in codes if state.get(c, '') < ref]
        log(f'[SCHED][UPDATE] ref={ref} total={len(codes)} todo={len(todo)}')
        print(f'[OK] 增量更新: 基准交易日 {ref}, 待更新 {len(todo)} 只')
    else:
        done = load_done()
        todo = [c for c in codes if c not in done]
        log(f'[SCHED] total={len(codes)} done={len(done)} todo={len(todo)}')
        print(f'[OK] 全量模式: 待处理 {len(todo)} 只')

    if not todo:
        print('[OK] 无待处理代码')
        return

    attempts = {}
    batch_no = 0
    while True:
        if update_mode:
            # 增量模式按实时状态刷新待办
            ref = last_trade_day()
            state = load_state()
            todo = [c for c in codes if state.get(c, '') < ref]
        else:
            done = load_done()
            todo = [c for c in codes if c not in done]
        if not todo:
            break
        batch = todo[:BATCH]
        ref_at_batch = ref if update_mode else None  # 批前快照, 用于判定本批是否推进
        batch_no += 1
        arg = ','.join(batch)
        mode_arg = ['--update'] if update_mode else []
        try:
            r = subprocess.run(
                [sys.executable, WORKER, arg] + mode_arg,
                capture_output=True, text=True, encoding='utf-8', timeout=TIMEOUT
            )
            log(f'  [{batch_no}] batch={len(batch)} rc={r.returncode} out={(r.stdout or "").strip()[-80:]}')
            if r.returncode != 0:
                log(f'  [{batch_no}] worker stderr: {(r.stderr or "")[:300]}')
            print(f'  [{batch_no}] {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "无输出"}')
        except subprocess.TimeoutExpired:
            log(f'  [{batch_no}] TIMEOUT（{TIMEOUT}s），已写事件保留，未完成股票将重试')
            print(f'  [{batch_no}] 超时，未完成的股票将重试')
        except Exception as e:
            log(f'  [{batch_no}] ERROR: {e}')
            print(f'  [{batch_no}] 错误 {e}')

        # 无进展的批次计数，超过 MAX_ATTEMPTS 放弃（可能是确定性失败）
        if update_mode:
            state = load_state()
            progressed = [c for c in batch if state.get(c, '') >= ref_at_batch]
        else:
            done = load_done()
            progressed = [c for c in batch if c in done]
        for c in batch:
            if c not in progressed:
                attempts[c] = attempts.get(c, 0) + 1
        stuck = [c for c, n in attempts.items() if n >= MAX_ATTEMPTS]
        if stuck:
            log(f'  [GIVEUP] {len(stuck)} 只连续{MAX_ATTEMPTS}次无进展，跳过: {stuck[:10]}...')
            print(f'  [GIVEUP] {len(stuck)} 只重试无进展，跳过（详见 {LOG_FILE}）')
            if not update_mode:
                with open(DONE_FILE, 'a', encoding='utf-8') as f:
                    for c in stuck:
                        f.write(c + '\n')
            else:
                # 增量模式下把放弃的代码状态推到基准日, 否则每轮都重试死循环
                with open(STATE_FILE, 'a', encoding='utf-8') as f:
                    for c in stuck:
                        f.write(f'{c},{ref_at_batch},0\n')
            attempts = {c: n for c, n in attempts.items() if n < MAX_ATTEMPTS}

    compact_state()
    final = len(load_state())
    log(f'[DONE] final state={final}')
    print(f'\n[OK] 调度完成，state={final}')

if __name__ == '__main__':
    main()
