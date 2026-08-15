# -*- coding: utf-8 -*-
"""
增量修复涨停数据：分批拉取 akshare 涨停池
每次 50 天，间隔 0.5s，断点续传
"""
import io, sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, 'data')
PROGRESS = os.path.join(DATA, '.fix_progress.json')

# 加载现有数据
zt = pd.read_csv(os.path.join(DATA, 'zt_events.csv'), names=['date','code','lianban'], dtype={'code': str})
zb = pd.read_csv(os.path.join(DATA, 'zhaban_events.csv'), names=['date','code'], dtype={'code': str})
s = pd.read_csv(os.path.join(DATA, 'sentiment_3y.csv'), parse_dates=['date'])

zt['code'] = zt['code'].astype(str).str.strip().str.zfill(6)
zb['code'] = zb['code'].astype(str).str.strip().str.zfill(6)

# 所有交易日
all_dates = sorted(s['date'].dt.strftime('%Y%m%d').unique().tolist())

# 加载进度
if os.path.exists(PROGRESS):
    done_dates = set(json.load(open(PROGRESS, encoding='utf-8')).get('done_dates', []))
else:
    done_dates = set()

remaining = [d for d in all_dates if d not in done_dates]
print(f'总共 {len(all_dates)} 天，已完成 {len(done_dates)}，剩余 {len(remaining)}')

import akshare as ak

new_rows = []
batch_size = 50
batch_count = 0

for i, date_str in enumerate(remaining):
    try:
        ak_zt = ak.stock_zt_pool_em(date=date_str)
        date_iso = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
        ak_codes = set(ak_zt['代码'].astype(str).str.strip().str.zfill(6).tolist())
        bs_codes = set(zt[zt['date'] == date_iso]['code'].tolist())
        missing = ak_codes - bs_codes
        
        if missing:
            for _, row in ak_zt[ak_zt['代码'].astype(str).str.zfill(6).isin(missing)].iterrows():
                code = str(row['代码']).strip().zfill(6)
                lb = 1
                for col in ['连板数', '连板']:
                    if col in ak_zt.columns and pd.notna(row.get(col)):
                        lb = int(row[col])
                        break
                new_rows.append({'date': date_iso, 'code': code, 'lianban': lb})
        
        done_dates.add(date_str)
        batch_count += 1
        
        if batch_count % 10 == 0:
            print(f'  [{batch_count}/{len(remaining)}] {date_str} 新增:{len(new_rows)}', flush=True)
        
        if batch_count % batch_size == 0:
            # 保存进度
            json.dump({'done_dates': list(done_dates)}, open(PROGRESS, 'w', encoding='utf-8'))
            time.sleep(0.3)
            
    except Exception as e:
        print(f'  [ERR] {date_str}: {e}', flush=True)
        time.sleep(1)
        continue

# 保存进度
json.dump({'done_dates': list(done_dates)}, open(PROGRESS, 'w', encoding='utf-8'))

# 合并
if new_rows:
    new_df = pd.DataFrame(new_rows)
    zt_fixed = pd.concat([zt, new_df], ignore_index=True)
    zt_fixed = zt_fixed.drop_duplicates(subset=['date','code'], keep='last')
    zt_fixed = zt_fixed.sort_values(['date','code']).reset_index(drop=True)
    zt_fixed.to_csv(os.path.join(DATA, 'zt_events.csv'), index=False, header=False, encoding='utf-8')
    print(f'\n[OK] zt_events.csv 已更新: {len(zt_fixed)} 条 (新增 {len(new_rows)})')
else:
    print(f'\n[OK] 无需补充')

# 重新聚合 sentiment
print('\n重新聚合 sentiment_3y.csv...')
days = {}
for ds, grp in zt_fixed.groupby('date'):
    lb = grp['lianban'].values
    days[ds] = {
        'zt_count': len(grp), 'lianban_height': int(lb.max()),
        'lianban2': int((lb == 2).sum()), 'lianban3': int((lb == 3).sum()),
        'lianban4p': int((lb >= 4).sum()), 'shouban': int((lb == 1).sum()),
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
out.to_csv(os.path.join(DATA, 'sentiment_3y.csv'), index=False, encoding='utf-8-sig')
print(f'[OK] sentiment_3y.csv: {len(out)} 天')
print(f'  zt_count 均值: {out.zt_count.mean():.1f} (原: {s.zt_count.mean():.1f})')
print(f'  zt_count 中位数: {out.zt_count.median():.1f} (原: {s.zt_count.median():.1f})')
print(f'\n  最近5天:')
print(out.tail(5)[['date','zt_count','zhaban_rate','lianban_height']].to_string(index=False))

# 重新生成 web 数据
print('\n重新生成 web 数据包...')
os.system(f'python {os.path.join(ROOT, "src", "sentiment", "gen_webdata.py")}')
print('\n[DONE] 全部修复完成')
