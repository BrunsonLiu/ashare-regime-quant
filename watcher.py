# -*- coding: utf-8 -*-
"""等待回测完成并自动生成可视化报告 (watcher)"""
import time, subprocess, sys

TARGET = "[BACKTEST_DONE]"
LOG = "backtest_run.log"
REPORT_LOG = "report_run.log"


def main():
    print("[watcher] 等待回测完成信号...", flush=True)
    while True:
        try:
            with open(LOG, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
        except Exception:
            txt = ""
        if TARGET in txt:
            print("[watcher] 检测到回测完成, 启动 report", flush=True)
            break
        time.sleep(5)

    with open(REPORT_LOG, "w", encoding="utf-8") as rl:
        rc = subprocess.run(
            [sys.executable, "-u", "main.py", "report"],
            stdout=rl, stderr=subprocess.STDOUT,
        )

    print("[watcher] REPORT_DONE rc=%d" % rc.returncode, flush=True)


if __name__ == "__main__":
    main()
