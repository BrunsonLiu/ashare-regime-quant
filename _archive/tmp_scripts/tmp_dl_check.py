# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

src = open('src/data_loader.py', encoding='utf-8').read()
for fn in ['def get_daily_data', 'def _save_cache', 'def load_cache', 'def get_daily_batch']:
    i = src.find(fn)
    if i >= 0:
        print('=' * 40, fn)
        print(src[i:i + 1100])
        print()
