# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
raw = open('data/zt_rebuild.log', 'rb').read()
for enc in ['utf-16', 'utf-8-sig', 'utf-8', 'gbk']:
    try:
        txt = raw.decode(enc)
        print(f'=== zt_rebuild.log 用 {enc} 解码，共 {len(txt.splitlines())} 行 ===')
        break
    except Exception:
        continue
lines = txt.splitlines()
for x in lines[:15]:
    print(repr(x))
print('...')
for x in lines[-15:]:
    print(repr(x))
