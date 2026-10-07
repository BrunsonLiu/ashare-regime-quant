# -*- coding: utf-8 -*-
"""
合并 2014-2023 补爬数据到主事件文件, 重新生成情绪数据
=========================================================
在 scripts/rebuild_sentiment_from_2014.py 完成后运行:
  python scripts/merge_pre2023_sentiment.py

效果: zt_events.csv 覆盖 2014起 → sentiment_3y.csv 覆盖 2014起,
      支持"只做A主线"的12年跨周期验证。
安全: 合并前备份原文件; 追加后按(date,code)去重。
"""
import os
import shutil
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8')

D = os.path.join(ROOT, 'data')


def merge_file(main_name, pre_name, cols):
    main_p = os.path.join(D, main_name)
    pre_p = os.path.join(D, pre_name)
    if not os.path.exists(pre_p) or os.path.getsize(pre_p) == 0:
        print(f'[SKIP] {pre_name} 不存在或为空')
        return
    main = pd.read_csv(main_p, header=None, names=cols, dtype={'code': str})
    pre = pd.read_csv(pre_p, header=None, names=cols, dtype={'code': str})
    before = len(main)
    combined = pd.concat([pre, main], ignore_index=True)
    combined = combined.drop_duplicates(subset=['date'] + (['code'] if 'code' in cols else []))
    combined = combined.sort_values('date')
    # 备份
    shutil.copy(main_p, main_p + '.bak')
    combined.to_csv(main_p, index=False, header=False, encoding='utf-8')
    print(f'[OK] {main_name}: {before} + {len(pre)} → 去重后 {len(combined)} 条'
          f' ({combined["date"].min()} ~ {combined["date"].max()})')


def main():
    merge_file('zt_events.csv', 'zt_events_pre2023.csv', ['date', 'code', 'lianban'])
    merge_file('zhaban_events.csv', 'zhaban_events_pre2023.csv', ['date', 'code'])
    print('\n重新聚合情绪数据...')
    from src.sentiment import aggregate_sentiment  # noqa: 执行即聚合
    print('[DONE] 情绪数据已扩展(见上方 aggregate 输出)')


if __name__ == '__main__':
    main()
