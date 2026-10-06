# -*- coding: utf-8 -*-
"""
增量修复涨停数据 v4：只补 akshare 可查的近期数据
akshare stock_zt_pool_em 只提供近期数据，无法回溯历史
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, 'data')

zt = pd.read_csv(os.path.join(DATA, 'zt_events.csv'), names=['date','code','lianban'], dtype={'code': str})
zb = pd.read_csv(os.path.join(DATA, 'zhaban_events.csv'), names=['date','code'], dtype={'code': str})
s = pd.read_csv(os.path.join(DATA, 'sentiment_3y.csv'), parse_dates=['date'])

zt['code'] = zt['code'].astype(str).str.strip().str.zfill(6)
zb['code'] = zb['code'].astype(str).str.strip().str.zfill(6)

# 修复 zt_events.csv 前导零
zt_fixed = zt.copy()
zt_fixed['code'] = zt_fixed['code'].astype(str).str.strip().str.zfill(6)
zt_fixed = zt_fixed.drop_duplicates(subset=['date','code'], keep='last')
zt_fixed = zt_fixed.sort_values(['date','code']).reset_index(drop=True)

print(f'zt_events: {len(zt_fixed)} 条 (原 {len(zt)})')
print(f'  前导零修复: {(zt["code"].str.len() != 6).sum()} 行已补零')

# 补近期 akshare 涨停池数据（最近10个交易日）
import akshare as ak
import time

recent_dates = sorted(s['date'].dt.strftime('%Y%m%d').unique().tolist())[-15:]
new_rows = []

for date_str in recent_dates:
    try:
        ak_zt = ak.stock_zt_pool_em(date=date_str)
        if len(ak_zt) == 0:
            continue
        
        date_iso = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
        code_col = '代码' if '代码' in ak_zt.columns else ak_zt.columns[1]
        lb_col = '连板数' if '连板数' in ak_zt.columns else None
        
        ak_codes = set(ak_zt[code_col].astype(str).str.strip().str.zfill(6).tolist())
        bs_codes = set(zt_fixed[zt_fixed['date'] == date_iso]['code'].tolist())
        missing = ak_codes - bs_codes
        
        if missing:
            for _, row in ak_zt.iterrows():
                code = str(row[code_col]).strip().zfill(6)
                if code not in missing:
                    continue
                lb = 1
                if lb_col and pd.notna(row.get(lb_col)):
                    try:
                        lb = int(row[lb_col])
                    except:
                        lb = 1
                new_rows.append({'date': date_iso, 'code': code, 'lianban': lb})
            print(f'  {date_str}: akshare={len(ak_codes)} bs={len(bs_codes)} 补充={len(missing)}')
        else:
            print(f'  {date_str}: akshare={len(ak_codes)} bs={len(bs_codes)} 无补充')
        
        time.sleep(0.5)
    except Exception as e:
        print(f'  {date_str}: ERR {str(e)[:80]}')
        continue

if new_rows:
    new_df = pd.DataFrame(new_rows)
    zt_fixed = pd.concat([zt_fixed, new_df], ignore_index=True)
    zt_fixed = zt_fixed.drop_duplicates(subset=['date','code'], keep='last')
    zt_fixed = zt_fixed.sort_values(['date','code']).reset_index(drop=True)

zt_fixed.to_csv(os.path.join(DATA, 'zt_events.csv'), index=False, header=False, encoding='utf-8')
print(f'\n[OK] zt_events.csv: {len(zt_fixed)} 条 (新增 {len(new_rows)})')

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
import subprocess
result = subprocess.run([sys.executable, os.path.join(ROOT, 'src', 'sentiment', 'gen_webdata.py')],
                       capture_output=True, text=True, encoding='utf-8')
print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
if result.stderr:
    print('STDERR:', result.stderr[-300:])

print('\n[DONE] 全部修复完成')
