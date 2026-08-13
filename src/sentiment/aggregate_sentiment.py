"""
聚合 zt_events.csv + zhaban_events.csv → sentiment_3y.csv
计算逐日：涨停家数/炸板率/连板高度/连板分布/首板占比
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ZT_FILE = os.path.join(ROOT, 'data', 'zt_events.csv')
ZHABAN_FILE = os.path.join(ROOT, 'data', 'zhaban_events.csv')
OUT_FILE = os.path.join(ROOT, 'data', 'sentiment_3y.csv')

zt = pd.read_csv(ZT_FILE, names=['date', 'code', 'lianban'])
zb = pd.read_csv(ZHABAN_FILE, names=['date', 'code'])

print(f'涨停事件 {len(zt)} 条，炸板事件 {len(zb)} 条')

# 逐日聚合
days = {}
for ds, grp in zt.groupby('date'):
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
    zt = r['zt_count']; zb = r['zhaban_count']
    rate = zb / max(zt + zb, 1)
    shouban_ratio = r['shouban'] / max(zt, 1)
    records.append({
        'date': ds, 'zt_count': zt, 'zhaban_count': zb,
        'zhaban_rate': round(rate, 4), 'lianban_height': r['lianban_height'],
        'lianban2': r['lianban2'], 'lianban3': r['lianban3'], 'lianban4p': r['lianban4p'],
        'shouban': r['shouban'], 'shouban_ratio': round(shouban_ratio, 4),
    })

out = pd.DataFrame(records)
out.to_csv(OUT_FILE, index=False, encoding='utf-8-sig')
print(f'\n[OK] 生成 data/sentiment_3y.csv：{len(out)} 天')
print(out.tail(8).to_string())
