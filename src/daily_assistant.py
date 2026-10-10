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
from src.utils.market_env import (MarketEnvironment, load_sentiment, hysteresis_confirm,
                                  ENV_DESC, ENV_EXPOSURE)
from src.data_loader import DataLoader


_HEALTH_CACHE = {}


def _industry_health():
    """行业长期健康度(带缓存)。依赖行业历史, 失败则返回空(不阻断)"""
    if 'data' in _HEALTH_CACHE:
        return _HEALTH_CACHE['data']
    try:
        from src.utils.industry_health import build_industry_index, health_score
        px, _ = build_industry_index()
        hs = health_score(px)
    except Exception as e:
        print(f'  [warn] 长期健康度不可用({e}), 跳过行业过滤')
        hs = {}
    _HEALTH_CACHE['data'] = hs
    return hs



def _main_industries_by_trend(top_n=5):
    """主线行业 = guardian 统一引擎口径(同花顺走势: 有前景 + 不接盘)。
    返回 (行业列表, 排名DataFrame)。"""
    try:
        from src.utils.ths_industry_rank import rank_industries
        from src.strategy.guardian import select_industries
        rk = rank_industries()
        inds = select_industries(top_n=top_n)   # 与回测同一函数
        if not inds:
            # 退化为纯榜单(数据不足时)
            inds = rk.head(top_n)['行业'].tolist()
        return inds, rk
    except Exception as e:
        print(f'  [warn] 行业走势不可用({e})')
        return [], None


def _leaders_in_industries(industries, pool_file='stock_pool_leaders_mc.csv', k=5):
    """指定行业内的龙头。
    行业口径: 同花顺(与行业指数一致) 优先用 ths_industry_map.csv;
    缺失则回退证监会龙头池(近似)。按市值排序取前k。"""
    fp = os.path.join(DATA_DIR, pool_file)
    if not os.path.exists(fp):
        fp = os.path.join(DATA_DIR, 'stock_pool_leaders.csv')
    pool = pd.read_csv(fp, dtype={'code': str})
    pool['code'] = pool['code'].str.zfill(6)
    # 同花顺行业映射(若存在)
    ths_map = {}
    tmf = os.path.join(DATA_DIR, 'ths_stock_industry.csv')
    if os.path.exists(tmf):
        tm = pd.read_csv(tmf, dtype={'code': str})
        tm['code'] = tm['code'].str.zfill(6)
        ths_map = dict(zip(tm['code'], tm['industry']))
    out = []
    for ind in industries:
        if ths_map:
            codes = [c for c, i in ths_map.items() if i == ind]
            g = pool[pool['code'].isin(codes)]
        else:
            g = pool[pool['industry'] == ind]
        for col in ('mktcap_yi', 'avg_amount_yi'):
            if col in g.columns:
                g = g.sort_values(col, ascending=False)
                break
        # 市值龙头取前 k*2 只, 再过"结构关"(力量/位置/博弈/节奏)
        picked = 0
        for _, r in g.head(k * 3).iterrows():
            if picked >= k:
                break
            s = _structure_of(r['code'], ind)
            rec = {'industry': ind, 'code': r['code'], 'name': r['name'],
                   'mktcap_yi': r.get('mktcap_yi'),
                   'structure': (s['博弈'] if s else '—'),
                   'veto': bool(s['否决']) if s else False,
                   'veto_reason': ('; '.join(s['理由']) if s and s['理由'] else '')}
            out.append(rec)
            picked += 1
    return pd.DataFrame(out)


_STRUCT_CACHE = {}


def _structure_of(code, industry):
    """单只股票的结构画像(带缓存), 失败返回None"""
    if code in _STRUCT_CACHE:
        return _STRUCT_CACHE[code]
    try:
        from src.utils.market_structure import analyze, load_industry_of
        from src.data_loader import DataLoader
        df = DataLoader().load_cache(code)
        r = analyze(df, industry_df=load_industry_of(code)) if df is not None else None
    except Exception:
        r = None
    _STRUCT_CACHE[code] = r
    return r


def _latest_industry_heat(days=5, top_n=5):
    """最近若干日的行业涨停热度(情绪主线)"""
    from src.backtest.sentiment_sector import build_industry_heat
    heat = build_industry_heat()
    last = heat['date'].max()
    recent = heat[heat['date'] > last - pd.Timedelta(days=int(days * 2))]
    agg = recent.groupby('industry').agg(zt=('zt_cnt', 'sum'), lb=('max_lb', 'max'))
    agg['热度'] = agg['zt'] + agg['lb'] * 3
    return agg.sort_values('热度', ascending=False).head(top_n), last


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
    sentiment = load_sentiment()
    envs, diag = env.classify_series(index_df, sentiment)
    # 用"指数 ∩ 情绪"都有数据的最后一天: 指数可能比情绪新(数据新鲜度不一致),
    # 若取指数最新日但情绪缺失 → 环境误判WARMUP
    sent_last = pd.to_datetime(sentiment['date']).max()
    valid_dates = [d for d in envs.keys() if d <= sent_last and envs.get(d) != 'WARMUP']
    last_date = max(valid_dates) if valid_dates else max(envs.keys())
    today_env = envs.get(last_date, 'WARMUP')
    row = diag[diag['date'] == last_date]
    why = row['why'].iloc[0] if len(row) else ''
    # 数据新鲜度提示
    idx_last = index_df['date'].max()
    if idx_last > sent_last:
        stale_days = int((idx_last - sent_last).days)
        if stale_days > 0:
            print('[提示] 情绪数据截至 %s, 指数到 %s(%d天差) → 环境判断用 %s; '
                  '建议运行: python -m src.sentiment.rebuild_scheduler --update'
                  % (sent_last.date(), idx_last.date(), stale_days, last_date.date()))

    # 滞后确认态(策略实际执行口径): 连续3天A才确认进入, 连续2天非A才退出
    confirmed_series = hysteresis_confirm(envs, enter_n=3, exit_n=2)
    confirmed_state = bool(confirmed_series.get(last_date, False))

    print('=' * 60)
    print(f'每日决策助手 · 数据截至 {last_date.date()}')
    print('=' * 60)
    print(f'\n【今日环境】{today_env}  —  {ENV_DESC.get(today_env, "数据不足")}')
    print(f'  判断依据: {why}')
    if today_env == 'A' and not confirmed_state:
        print('  [确认中] A环境未满3天确认, 策略暂不入场(守则: 主线需持续3天)')

    # 操作建议以确认态为准(策略实际执行口径)
    if today_env == 'A':
        action = ('✓ A环境已确认, 可持仓(做主线龙头, 让利润奔跑)' if confirmed_state
                  else '⏳ A环境确认中(未满3天) —— 策略暂空仓等待')
        exposure = ENV_EXPOSURE['A'] if confirmed_state else 0.0
    else:
        exposure = ENV_EXPOSURE.get(today_env, 0)
        action = {
            'B': '轻仓或空仓(主线散乱, 追热点易被套)',
            'C': '轻仓快进快出(超跌反弹, 严格止损)',
            'D': '建议空仓观望(均线空头, 保存实力)',
        }.get(today_env, '数据不足')
    print(f'  操作建议: {action}')
    print(f'  仓位上限: {int(exposure*100)}%')

    # === 主线行业: guardian 统一口径(有前景 + 不接盘) ===
    print(f'\n【主线行业】(有前景 ∩ 不接盘, 同花顺口径)')
    inds_by_trend, rk = _main_industries_by_trend(top_n=8)
    if rk is not None and len(rk):
        print(f'  {"行业":<10}{"近1年":>8}{"近3年":>9}{"距高点":>8}  状态')
        for n in rk['行业'].tolist()[:12]:
            try:
                from src.strategy.guardian import _industry_index, _industry_score
                idx = _industry_index(n)
                sc = _industry_score(idx, None) if idx is not None else None
            except Exception:
                sc = None
            if not sc:
                continue
            if sc['入选']:
                state = '✓ 入选'
            elif not sc['有前景']:
                state = '✗ 无前景(长期走弱)'
            elif sc['距高点%'] > -3:
                state = '✗ 高位(会接盘,等回调)'
            elif sc['距高点%'] < -35:
                state = '✗ 深跌(接刀风险)'
            elif (sc.get('近20日%') or 0) >= 15:
                state = '✗ 短期过热'
            else:
                state = '✗ 剔除'
            print(f'  {n[:9]:<10}{sc["近1年%"]:+7.0f}%{sc["近3年%"]:+8.0f}%{sc["距高点%"]:+7.0f}%  {state}')
        print('  入选=有前景 且 位置合适(-35%~-3%), 不过热; 其余按原因标注剔除')
        print('  长期最弱应回避: ' + ', '.join(
            f'{r["行业"]}{r["近1年%"]:+.0f}%' for _, r in rk.tail(3).iterrows()))
    else:
        print('  [warn] 行业走势数据不可用')

    # 涨停热度降级为"市场温度"(不再用于选行业)
    heat, hdate = _latest_industry_heat()
    mkt_temp = heat['热度'].sum()
    print(f'\n【市场温度】(辅助, 不用于选行业) 情绪热点行业涨停热度合计: {int(mkt_temp)}')

    # 建议标的: 从"长期走势强"的行业里取市值龙头
    industries = inds_by_trend[:3]
    leaders = _leaders_in_industries(industries) if industries else pd.DataFrame()
    print(f'\n【候选龙头】(强势行业 ∩ 市值龙头 ∩ 结构过关)')
    print('  [结构]列: 游资/题材/高位=否决; 机构/龙头领先=可关注')
    for ind in industries:
        rows = leaders[leaders['industry'] == ind]
        for _, r in rows.head(3).iterrows():
            tag = '✗' if r.get('veto') else '○'
            reason = f"  <- {r['veto_reason']}" if r.get('veto') else ''
            print(f'  {tag} {ind[:12]:<14} {r["name"]}({r["code"]})  {r.get("structure","")}{reason}')
    if len(leaders):
        n_veto = int(leaders['veto'].sum())
        if n_veto:
            print(f'  (其中 {n_veto} 只被结构否决: 游资/题材/高位接盘, 不建议碰)')

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
    return {'env': today_env, 'confirmed': confirmed_state, 'exposure': exposure,
            'industries': industries, 'industry_rank': (rk.head(12).to_dict('records')
                                                        if rk is not None and len(rk) else []),
            'leaders': leaders, 'heat': list(heat.iterrows()), 'why': why, 'action': action}


if __name__ == '__main__':
    hold = None
    if '--hold' in sys.argv:
        i = sys.argv.index('--hold')
        if i + 1 < len(sys.argv):
            hold = sys.argv[i + 1].split(',')
    daily_report(hold)
