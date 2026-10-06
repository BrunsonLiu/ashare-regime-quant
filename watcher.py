# -*- coding: utf-8 -*-
"""等待回测完成并自动生成可视化报告 (watcher)

完成信号: backtest_run.log 中出现 [BACKTEST_DONE]，且日志修改时间晚于本脚本启动时间。
（main.py backtest 会打印该标记；用 mtime 判新避免上一轮的旧记录误触发）
"""
import time, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = "[BACKTEST_DONE]"
LOG = os.path.join(BASE, "backtest_run.log")
REPORT_LOG = os.path.join(BASE, "report_run.log")
TIMEOUT_SEC = 2 * 3600  # 最多等2小时


def main():
    start_ts = time.time()
    print(f"[watcher] 等待回测完成信号 ({LOG})...", flush=True)
    triggered = False
    while time.time() - start_ts <= TIMEOUT_SEC:
        try:
            if os.path.getmtime(LOG) >= start_ts:
                with open(LOG, "r", encoding="utf-8", errors="ignore") as f:
                    if TARGET in f.read():
                        triggered = True
                        break
        except OSError:
            pass
        time.sleep(5)

    if not triggered:
        print("[watcher] 超时未检测到回测完成信号，退出", flush=True)
        return

    print("[watcher] 检测到回测完成, 启动 report", flush=True)
    with open(REPORT_LOG, "w", encoding="utf-8") as rl:
        rc = subprocess.run(
            [sys.executable, "-u", "main.py", "report"],
            cwd=BASE, stdout=rl, stderr=subprocess.STDOUT,
        )

    print("[watcher] REPORT_DONE rc=%d" % rc.returncode, flush=True)


if __name__ == "__main__":
    main()
