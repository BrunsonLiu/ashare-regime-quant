"""
确认涨停池历史边界：找到能拿到数据的最后日期
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import akshare as ak

# 从最近的日期往回测
for d in ['20260812', '20260811', '20260810', '20260807', '20260806', '20260805', '20260804', '20260803', '20260731', '20260730', '20260725', '20260720', '20260715', '20260710', '20260701', '20260630', '20260620']:
    try:
        df = ak.stock_zt_pool_em(date=d)
        print(f'  {d}: {len(df)}只')
    except Exception as e:
        print(f'  {d}: [X] {str(e)[:50]}')
