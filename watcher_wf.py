"""walk-forward 完成后自动生成报告（基于文件存在检测，不读日志，规避编码问题）"""
import time, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(BASE, 'data', 'walkforward.csv')
REPORT = [sys.executable, 'main.py', 'report']


def main():
    for _ in range(720):  # 最多等 60 分钟
        if os.path.exists(TARGET):
            print('[WATCHER] walkforward 完成，生成报告...', flush=True)
            try:
                subprocess.run(REPORT, cwd=BASE, check=True)
                print('[WATCHER] 报告生成完毕', flush=True)
            except Exception as e:
                print(f'[WATCHER] 报告失败: {e}', flush=True)
            return
        time.sleep(5)
    print('[WATCHER] 超时未检测到 walkforward.csv', flush=True)


if __name__ == '__main__':
    main()
