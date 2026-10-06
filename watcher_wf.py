"""walk-forward 完成后自动生成报告（基于文件检测）

判新条件: walkforward.csv 存在且 mtime 晚于本脚本启动时间——
文件由 run_walkforward 常驻保留，仅凭"存在"会把旧文件误判成本轮完成。
"""
import time, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(BASE, 'data', 'walkforward.csv')
REPORT = [sys.executable, 'main.py', 'report']
TIMEOUT_SEC = 60 * 60  # 最多等60分钟


def main():
    start_ts = time.time()
    while time.time() - start_ts <= TIMEOUT_SEC:
        try:
            if os.path.exists(TARGET) and os.path.getmtime(TARGET) >= start_ts:
                print('[WATCHER] walkforward 完成，生成报告...', flush=True)
                try:
                    subprocess.run(REPORT, cwd=BASE, check=True)
                    print('[WATCHER] 报告生成完毕', flush=True)
                except Exception as e:
                    print(f'[WATCHER] 报告失败: {e}', flush=True)
                return
        except OSError:
            pass
        time.sleep(5)
    print('[WATCHER] 超时未检测到新的 walkforward.csv', flush=True)


if __name__ == '__main__':
    main()
