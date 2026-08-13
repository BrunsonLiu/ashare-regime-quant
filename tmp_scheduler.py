"""
外层调度：读取待处理股票，每30只启动一个全新子进程处理
子进程独立连接、独立内存，处理完退出 → 彻底避免连接老化/内存累积
断点续传：done文件已有的一定跳过
"""
import sys, os, subprocess, time
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

BATCH = 30
DONE_FILE = 'data/zt_done.txt'
LOG_FILE = 'data/zt_rebuild.log'

def get_pool_codes():
    df = pd.read_csv('data/stock_pool.csv')
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
    todo = [c for c in codes if c not in done]
    log(f'[SCHED] total={len(codes)} done={len(done)} todo={len(todo)}')
    print(f'[OK] 待处理 {len(todo)} 只')

    for i in range(0, len(todo), BATCH):
        batch = todo[i:i+BATCH]
        arg = ','.join(batch)
        try:
            r = subprocess.run(
                [sys.executable, 'tmp_worker.py', arg],
                capture_output=True, text=True, encoding='utf-8', timeout=120
            )
            new_done = len(load_done())
            log(f'  [{i//BATCH+1}] batch={len(batch)} done_total={new_done}')
            print(f'  [{i//BATCH+1}] 累计 {new_done}/{len(codes)}')
        except subprocess.TimeoutExpired:
            log(f'  [{i//BATCH+1}] TIMEOUT, 跳过这批(可能部分完成)')
            print(f'  [{i//BATCH+1}] 超时跳过')
        except Exception as e:
            log(f'  [{i//BATCH+1}] ERROR: {e}')
            print(f'  [{i//BATCH+1}] 错误 {e}')

    final = len(load_done())
    log(f'[DONE] final done={final}')
    print(f'\n[OK] 全部调度完成，done={final}')

if __name__ == '__main__':
    main()
