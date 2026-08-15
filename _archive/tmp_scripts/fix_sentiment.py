# -*- coding: utf-8 -*-
"""
修复数据：1) 补科创板688  2) 重跑被异常吞掉的涨停判定  3) 重新聚合
策略：用 akshare 涨停池做交叉验证，不重跑 baostock（太慢且不稳定）
"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, 'data')

# 1) 加载现有数据
zt = pd.read_csv(os.path.join(DATA, 'zt_events.csv'), names=['date','code','lianban'], dtype={'code': str})
zb = pd.read_csv(os.path.join(DATA, 'zhaban_events.csv'), names=['date','code'], dtype={'code': str})
s = pd.read_csv(os.path.join(DATA, 'sentiment_3y.csv'), parse_dates=['date'])

# 确保 code 是 6 位字符串
zt['code'] = zt['code'].astype(str).str.strip().str.zfill(6)
zb['code'] = zb['code'].astype(str).str.strip().str.zfill(6)

print(f'原始数据: zt={len(zt)} zb={len(zb)} sentiment={len(s)}')
print(f'zt date range: {zt.date.min()} ~ {zt.date.max()}')
print(f'zt unique codes: {zt.code.nunique()}')

# 2) 用 akshare 涨停池补数据
import akshare as ak

dates_to_check = sorted(s['date'].dt.strftime('%Y%m%d').unique().tolist())
print(f'\n需要检查 {len(dates_to_check)} 个交易日的涨停池...')

new_zt_rows = []
new_zb_rows = []

for i, date_str in enumerate(dates_to_check):
    try:
        ak_zt = ak.stock_zt_pool_em(date=date_str)
        ak_zt_codes = set(ak_zt['代码'].astype(str).str.strip().str.zfill(6).tolist())
        
        # 当前 baostock 已有的
        date_iso = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
        bs_codes = set(zt[zt['date'] == date_iso]['code'].tolist())
        
        # 缺失的
        missing = ak_zt_codes - bs_codes
        if missing:
            # 从 akshare 获取连板数
            for _, row in ak_zt[ak_zt['代码'].astype(str).str.zfill(6).isin(missing)].iterrows():
                code = str(row['代码']).strip().zfill(6)
                lb = int(row.get('连板数', 1)) if pd.notna(row.get('连板数')) else 1
                new_zt_rows.append({'date': date_iso, 'code': code, 'lianban': lb})
        
        if (i + 1) % 50 == 0:
            print(f'  进度: {i+1}/{len(dates_to_check)}  新增涨停: {len(new_zt_rows)}')
    except Exception as e:
        pass  # 非交易日或接口异常

print(f'\n补全完成: 新增涨停事件 {len(new_zt_rows)} 条')

# 3) 合并
if new_zt_rows:
    new_zt_df = pd.DataFrame(new_zt_rows)
    zt_fixed = pd.concat([zt, new_zt_df], ignore_index=True)
    zt_fixed = zt_fixed.drop_duplicates(subset=['date','code'], keep='last')
    zt_fixed = zt_fixed.sort_values(['date','code']).reset_index(drop=True)
else:
    zt_fixed = zt.sort_values(['date','code']).reset_index(drop=True)

# 4) 重新聚合
days = {}
for ds, grp in zt_fixed.groupby('date'):
    lb = grp['lianban'].values
    days[ds] = {
        'zt_count': len(grp),
        'lianban_height': int(lb.max()),
        'lianban2': int((lb == 2).sum()),
        'lianban3': int((lb == 3).sum()),
        'lianban4p': int((lb >= 4).sum()),
        'shouban': int((lb == 1).sum()),
        'zhaban_count': 0,
    }
for ds, grp in zb.groupby('date'):
    if ds not in days:
        days[ds] = {'zt_count': 0, 'lianban_height': 0, 'lianban2': 0, 'lianban3': 0, 'lianban4p': 0, 'shouban': 0, 'zhaban_count': 0}
    days[ds]['zhaban_count'] = len(grp)

records = []
for ds in sorted(days.keys()):
    r = days[ds]
    zc = r['zt_count']; zbc = r['zhaban_count']
    rate = zbc / max(zc + zbc, 1)
    sr = r['shouban'] / max(zc, 1)
    records.append({
        'date': ds, 'zt_count': zc, 'zhaban_count': zbc,
        'zhaban_rate': round(rate, 4), 'lianban_height': r['lianban_height'],
        'lianban2': r['lianban2'], 'lianban3': r['lianban3'], 'lianban4p': r['lianban4p'],
        'shouban': r['shouban'], 'shouban_ratio': round(sr, 4),
    })

out = pd.DataFrame(records)
out_path = os.path.join(DATA, 'sentiment_3y.csv')
out.to_csv(out_path, index=False, encoding='utf-8-sig')
print(f'\n[OK] 重新生成 sentiment_3y.csv: {len(out)} 天')
print(f'  zt_count 均值: {out.zt_count.mean():.1f} (原: {s.zt_count.mean():.1f})')
print(f'  zt_count 中位数: {out.zt_count.median():.1f} (原: {s.zt_count.median():.1f})')
print(f'\n  最近5天:')
print(out.tail(5)[['date','zt_count','zhaban_rate','lianban_height']].to_string(index=False))

# 保存修复后的 zt_events
zt_fixed.to_csv(os.path.join(DATA, 'zt_events.csv'), index=False, header=False, encoding='utf-8')
print(f'\n[OK] zt_events.csv 已更新: {len(zt_fixed)} 条 (原: {len(zt)})')
