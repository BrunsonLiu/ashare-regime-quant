# -*- coding: utf-8 -*-
"""
数据世界观 —— 一眼看清所有数据集的新鲜度与契约健康
用法: python main.py manifest
"""
import os
import sys
import json

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR

# 文件 → (必需列, 日期列, 是否无表头)
# 事件/状态文件由 worker 追加写入, 无表头行, 消费方以 names= 读取
CONTRACTS = {
    'sentiment_3y.csv': (
        ['date', 'zt_count', 'zhaban_count', 'zhaban_rate', 'lianban_height',
         'lianban2', 'lianban3', 'lianban4p', 'shouban', 'shouban_ratio'], 'date', False),
    'backtest_equity.csv': (
        ['date', 'equity', 'cash', 'positions', 'regime', 'position_pct'], 'date', False),
    'backtest_trades.csv': (
        ['date', 'code', 'action', 'price', 'shares', 'cost_basis',
         'pnl', 'pnl_pct', 'reason'], 'date', False),
    'walkforward.csv': (['seg', 'start', 'end', 'ret_pct', 'max_dd_pct'], 'start', False),
    'stock_pool.csv': (['code', 'name'], None, False),
    'index_000001.csv': (['date', 'open', 'high', 'low', 'close', 'volume'], 'date', False),
    'zt_events.csv': (['date', 'code', 'lianban'], 'date', True),
    'zhaban_events.csv': (['date', 'code'], 'date', True),
    'zt_state.csv': (['code', 'last_date', 'lianban'], None, True),
}


def build_manifest(data_dir=DATA_DIR):
    """返回 [{file, exists, rows, last_date, columns_ok, missing}]"""
    rows = []
    for name, (required, date_col, headerless) in CONTRACTS.items():
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            rows.append({'file': name, 'exists': False, 'rows': None,
                         'last_date': '--', 'columns_ok': '--', 'missing': '文件不存在'})
            continue
        try:
            if headerless:
                df = pd.read_csv(path, header=None, names=required)
            else:
                df = pd.read_csv(path)
            missing = [c for c in required if c not in df.columns]
            last = ''
            if date_col and date_col in df.columns:
                last = str(pd.to_datetime(df[date_col]).max().date())
            rows.append({
                'file': name, 'exists': True, 'rows': len(df),
                'last_date': last or '--',
                'columns_ok': 'OK' if not missing else 'FAIL',
                'missing': ','.join(missing) if missing else '',
            })
        except Exception as e:
            rows.append({'file': name, 'exists': True, 'rows': None,
                         'last_date': '--', 'columns_ok': 'FAIL', 'missing': str(e)[:60]})

    # 日线缓存(整体概览: 文件数与抽样新鲜度)
    daily_dir = os.path.join(data_dir, 'daily')
    if os.path.isdir(daily_dir):
        files = [f for f in os.listdir(daily_dir) if f.endswith('.csv')]
        rows.append({'file': 'daily/*.csv', 'exists': True, 'rows': len(files),
                     'last_date': '(抽样见下)', 'columns_ok': '--', 'missing': ''})
        if files:
            sample = pd.read_csv(os.path.join(daily_dir, files[len(files) // 2]))
            rows.append({'file': f'daily/{files[len(files)//2]} (抽样)',
                         'exists': True, 'rows': len(sample),
                         'last_date': str(pd.to_datetime(sample['date']).max().date()),
                         'columns_ok': 'OK' if all(c in sample.columns for c in
                                                   ['date', 'open', 'high', 'low', 'close', 'volume']) else 'FAIL',
                         'missing': ''})

    # web/data JSON 严格可解析性(浏览器口径)
    web_dir = os.path.join(os.path.dirname(data_dir), 'web', 'data')
    if os.path.isdir(web_dir):
        bad = []
        for f in sorted(os.listdir(web_dir)):
            if not f.endswith('.json'):
                continue
            try:
                json.loads(open(os.path.join(web_dir, f), encoding='utf-8').read(),
                           parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
            except Exception:
                bad.append(f)
        rows.append({'file': f'web/data/*.json', 'exists': True,
                     'rows': len([f for f in os.listdir(web_dir) if f.endswith('.json')]),
                     'last_date': '--',
                     'columns_ok': 'OK' if not bad else 'FAIL',
                     'missing': '非法JSON: ' + ','.join(bad) if bad else ''})
    return pd.DataFrame(rows)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    df = build_manifest()
    print('=== 数据世界观 (data manifest) ===')
    print(df.to_string(index=False))
    stale = df[(df['exists'] == True) & (df['columns_ok'] == 'FAIL')]
    if len(stale):
        print(f'\n[!!] {len(stale)} 个数据集契约异常, 见 missing 列')
    else:
        print('\n[OK] 全部数据集契约健康')


if __name__ == '__main__':
    main()
