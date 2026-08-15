# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
raw = open('data/sch.txt', 'rb').read()
print('前4字节:', raw[:4])
# 尝试 utf-16
for enc in ['utf-16', 'utf-8-sig', 'gbk']:
    try:
        txt = raw.decode(enc)
        print(f'=== 用 {enc} 解码成功 ===')
        break
    except Exception as e:
        print(enc, '失败', e)

lines = txt.splitlines()
print('总行数:', len(lines))
print('开头8行:')
for x in lines[:8]:
    print(repr(x))
print('结尾8行:')
for x in lines[-8:]:
    print(repr(x))
