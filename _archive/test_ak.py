import akshare as ak, sys, os
sys.stdout.reconfigure(encoding='utf-8')

tests = [
    ('stock_zt_pool_em', 'ZhangTing'),
    ('stock_zt_pool_strong_em', 'LianBan'),
    ('stock_zt_pool_zbgc_em', 'ZhaBan'),
    ('stock_lhb_detail_em', 'LongHuBang'),
    ('stock_hsgt_hist_em', 'NorthMoney'),
    ('stock_sector_fund_flow_rank', 'SectorFlow'),
    ('stock_individual_fund_flow', 'StockFlow'),
    ('stock_board_concept_name_em', 'ConceptBoard'),
    ('stock_board_industry_name_em', 'IndustryBoard'),
]

for func_name, desc in tests:
    try:
        f = getattr(ak, func_name, None)
        if f is None:
            print(f'[X] {desc}: not found')
            continue
        df = f()
        print(f'[OK] {desc}: shape={df.shape}, cols={list(df.columns[:10])}')
    except Exception as e:
        print(f'[!!] {desc}: {type(e).__name__}: {e}')
