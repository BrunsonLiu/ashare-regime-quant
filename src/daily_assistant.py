# -*- coding: utf-8 -*-
"""
每日决策助手 —— 把守则策略变成可用工具
=========================================
基于已验证的结论(STRATEGY_CONCLUSION.md):
  龙头池 + 只在A环境持有 + 低换手

输出(每日收盘后可跑):
  1. 今日环境(A/B/C/D) + 判断依据
  2. 是否应持仓 + 建议仓位上限
  3. 当前主线行业(情绪热度)
  4. 建议关注的龙头(该行业内)
  5. 与当前持仓的差异提示(该换/该拿/该清)

用法: python main.py daily            # 打印今日建议
      python main.py daily --hold 600519,000858   # 结合当前持仓给调仓提示
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import DATA_DIR
from src.utils.market_env import MarketEnvironment, load_sentiment, ENV_DESC, ENV_EXPOSURE
from src.data_loader import DataLoader


def _latest_industry_heat(days=5, top_n=5):
    """最近若干日的行业涨停热度(情绪主线)"""
    from src.backtest.sentiment_sector import build_industry_heat
    heat = build_industry_heat()
    last = heat['date'].max()
    recent = heat[heat['date'] > last - pd.Timedelta(days=days * 2)]
    agg = recent.groupby('industry').agg(zt=('zt_cnt', 'sum'), lb=('max_lb', 'max'))
    agg['热度'] = agg['zt'] + agg['lb'] * 3
    return agg.sort_values('热度', ascending=False).head(top_n), last


def _leaders_in_industries(industries, pool_file='stock_pool_leaders.csv', k=5):
    """指定行业内的龙头(按成交额/PIT排名)"""
    pool = pd.read_csv(os.path.join(DATA_DIR, pool_file), dtype={'code': str})
    pool['code'] = pool['code'].str.zfill(6)
    out = []
    for ind in industries:
        g = pool[pool['industry'] == ind]
        col = 'avg_amount_yi' if 'avg_amount_yi' in g.columns else None
        if col:
            g = g.sort_values(col, ascending=False)
        for _, r in g.head(k).iterrows():
            out.append({'industry': ind, 'code': r['code'], 'name': r['name']})
    return pd.DataFrame(out)


def daily_report(hold_codes=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass  # 输出被重定向(测试)时无 reconfigure 属性
    loader = DataLoader()
    index_df = loader.get_index_data('000001', days=400)
    if index_df is None or len(index_df) == 0:
        print('[!] 指数数据不可用'); return
    index_df['date'] = pd.to_datetime(index_df['date'])

    env = MarketEnvironment()
    envs, diag = env.classify_series(index_df, load_sentiment())
    last_date = max(envs.keys())
    today_env = envs.get(last_date, 'WARMUP')
    row = diag[diag['date'] == last_date]
    why = row['why'].iloc[0] if len(row) else ''

    print('=' * 60)
    print(f'每日决策助手 · 数据截至 {last_date.date()}')
    print('=' * 60)
    print(f'\n【今日环境】{today_env}  —  {ENV_DESC.get(today_env, "数据不足")}')
    print(f'  判断依据: {why}')

    exposure = ENV_EXPOSURE.get(today_env, 0)
    action = {
        'A': '可持仓, 建议仓位上限80%(做主线龙头, 让利润奔跑)',
        'B': '轻仓或空仓(主线散乱, 追热点易被套)',
        'C': '轻仓快进快出(超跌反弹, 严格止损)',
        'D': '建议空仓观望(均线空头, 保存实力)',
    }.get(today_env, '数据不足')
    print(f'  操作建议: {action}')
    print(f'  仓位上限: {int(exposure*100)}%')

    # 主线行业
    heat, hdate = _latest_industry_heat()
    print(f'\n【当前情绪主线】(截至 {hdate.date()}, 涨停热度=涨停家数+连板高度×3)')
    for ind, r in heat.iterrows():
        print(f'  {ind[:24]:<26} 涨停{int(r["zt"]):>3}家  最高{int(r["lb"])}连板  热度{int(r["热度"])}')

    # 建议标的
    industries = list(heat.index[:3])
    leaders = _leaders_in_industries(industries)
    print(f'\n【建议关注龙头】(按行业龙头池)')
    for ind in industries:
        names = leaders[leaders['industry'] == ind]
        s = ' | '.join(f'{r["name"]}({r["code"]})' for _, r in names.head(3).iterrows())
        print(f'  {ind[:20]:<22} {s}')

    # 持仓提示
    if hold_codes:
        print(f'\n【持仓检查】当前持仓: {", ".join(hold_codes)}')
        if today_env in ('B', 'D'):
            print(f'  ⚠ 当前环境为 {today_env}, 按守则应轻仓/空仓 → 考虑减仓或清仓')
        elif today_env == 'A':
            print(f'  ✓ A主线环境, 可持有; 若持有不在主线内的可考虑换到主线龙头')
        held_in_main = set(hold_codes) & set(leaders['code'])
        if held_in_main:
            print(f'  ✓ 其中 {len(held_in_main)} 只在当前主线内: {", ".join(held_in_main)}')

    print('\n' + '=' * 60)
    print('说明: 本工具基于3.5年历史验证(STRATEGY_CONCLUSION.md), 不构成投资建议。')
    return {'env': today_env, 'exposure': exposure, 'industries': industries,
            'leaders': leaders}


if __name__ == '__main__':
    hold = None
    if '--hold' in sys.argv:
        i = sys.argv.index('--hold')
        if i + 1 < len(sys.argv):
            hold = sys.argv[i + 1].split(',')
    daily_report(hold)
