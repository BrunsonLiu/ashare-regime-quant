"""
外层调度：读取待处理股票，每30只启动一个全新子进程处理
子进程独立连接、独立内存，处理完退出 → 彻底避免连接老化/内存累积
断点续传：done文件已有的一定跳过；失败的股票（fail记录/done未标记）自动重试，最多MAX_ATTEMPTS次
"""
import sys, os, subprocess, time
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

# 项目根目录（本文件位于 src/sentiment/ 下，向上两级）
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rebuild_worker.py')

BATCH = 30
MAX_ATTEMPTS = 2        # 同一批最多重试次数，防止确定性失败导致死循环
TIMEOUT = 900           # 30只 × 每只数秒 + 登录，120s 必超时强杀
DONE_FILE = os.path.join(ROOT, 'data', 'zt_done.txt')
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

def log(msg):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def main():
    codes = get_pool_codes()
    done = load_done()
    log(f'[SCHED] total={len(codes)} done={len(done)}')
    todo = [c for c in codes if c not in done]
    print(f'[OK] 待处理 {len(todo)} 只')

    attempts = {}
    batch_no = 0
    while True:
        done = load_done()
        todo = [c for c in codes if c not in done]
        if not todo:
            break
        batch = todo[:BATCH]
        batch_no += 1
        arg = ','.join(batch)
        try:
            r = subprocess.run(
                [sys.executable, WORKER, arg],
                capture_output=True, text=True, encoding='utf-8', timeout=TIMEOUT
            )
            new_done = load_done()
            progressed = sum(1 for c in batch if c in new_done)
            log(f'  [{batch_no}] batch={len(batch)} progressed={progressed} rc={r.returncode} done_total={len(new_done)}')
            if r.returncode != 0:
                log(f'  [{batch_no}] worker stderr: {(r.stderr or "")[:300]}')
            print(f'  [{batch_no}] 本批推进 {progressed}/{len(batch)}，累计 {len(new_done)}/{len(codes)}')
        except subprocess.TimeoutExpired:
            log(f'  [{batch_no}] TIMEOUT（{TIMEOUT}s），已写事件保留，未完成股票将重试')
            print(f'  [{batch_no}] 超时，未完成的股票将重试')
        except Exception as e:
            log(f'  [{batch_no}] ERROR: {e}')
            print(f'  [{batch_no}] 错误 {e}')

        # 无进展的批次计数，超过 MAX_ATTEMPTS 放弃（可能是确定性失败）
        new_done = load_done()
        progressed = [c for c in batch if c in new_done]
        for c in batch:
            if c not in progressed:
                attempts[c] = attempts.get(c, 0) + 1
        stuck = [c for c, n in attempts.items() if n >= MAX_ATTEMPTS]
        if stuck:
            log(f'  [GIVEUP] {len(stuck)} 只连续{MAX_ATTEMPTS}次无进展，跳过: {stuck[:10]}...')
            print(f'  [GIVEUP] {len(stuck)} 只重试无进展，跳过（详见 {LOG_FILE}）')
            with open(DONE_FILE, 'a', encoding='utf-8') as f:
                for c in stuck:
                    f.write(c + '\n')
            attempts = {c: n for c, n in attempts.items() if n < MAX_ATTEMPTS}

    final = len(load_done())
    log(f'[DONE] final done={final}')
    print(f'\n[OK] 全部调度完成，done={final}')

if __name__ == '__main__':
    main()
