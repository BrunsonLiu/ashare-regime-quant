# -*- coding: utf-8 -*-
"""
生成全量前端数据包 v2 — 覆盖所有模块
扩展 gen_webdata.py，新增 6 个模块的数据生成
"""
import json, os, sys, math
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'web', 'data')
os.makedirs(OUT, exist_ok=True)

# 先运行原始 gen_webdata 的逻辑
sys.path.insert(0, ROOT)
from src.sentiment.gen_webdata import generate as generate_base_data, json_dump_safe


# === 6. 市场状态数据 ===
def gen_regime_data():
    """生成市场状态判断数据"""
    from src.data_loader import DataLoader
    from src.utils.market_regime import MarketRegime

    loader = DataLoader()
    index_df = loader.get_index_data("000001", days=300)

    if index_df is None or len(index_df) == 0:
        print('[SKIP] regime.json: 指数数据不可用')
        return

    regime = MarketRegime()
    
    # 逐日计算状态
    records = []
    close = index_df['close']
    ma_short = close.rolling(20).mean()
    ma_long = close.rolling(60).mean()
    vol = close.pct_change().rolling(20).std()
    
    for i in range(60, len(index_df)):
        sub = index_df.iloc[:i+1]
        result = regime.detect(sub)
        records.append({
            'date': str(index_df.iloc[i]['date'])[:10],
            'close': round(float(close.iloc[i]), 2),
            'ma20': round(float(ma_short.iloc[i]), 2) if pd.notna(ma_short.iloc[i]) else None,
            'ma60': round(float(ma_long.iloc[i]), 2) if pd.notna(ma_long.iloc[i]) else None,
            'volatility': round(float(vol.iloc[i]) * 100, 2) if pd.notna(vol.iloc[i]) else None,
            'regime': result['regime'],
            'bull_score': result['bull_score'],
            'bear_score': result['bear_score'],
            'slow_bull_score': result['slow_bull_score'],
            'trend_strength': result['trend_strength'],
            'recent_return': result['recent_return'],
            'drawdown_from_120high': result['drawdown_from_120high'],
        })
    
    # 最新状态详情
    latest = regime.detect(index_df)
    
    regime_data = {
        'history': records,
        'current': {
            'regime': latest['regime'],
            'description': latest['description'],
            'ma_short': latest['ma_short'],
            'ma_long': latest['ma_long'],
            'volatility': latest['volatility'],
            'trend_strength': latest['trend_strength'],
            'recent_return': latest['recent_return'],
            'vol_trend': latest['vol_trend'],
            'bull_score': latest['bull_score'],
            'bear_score': latest['bear_score'],
            'slow_bull_score': latest['slow_bull_score'],
            'policy_bias': latest['policy_bias'],
            'policy_note': latest['policy_note'],
            'drawdown_from_120high': latest['drawdown_from_120high'],
            'high_120': latest['high_120'],
            'position_advice': latest['position_advice'],
        },
    }
    
    with open(os.path.join(OUT, 'regime.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(regime_data, f, default=str)
    print(f'[OK] regime.json: {len(records)} days, current={latest["regime"]}')


# === 7. 实时市场概览数据 ===
def gen_live_data():
    """生成实时市场概览数据（快照）"""
    from src.direct_data import get_fetcher
    fetcher = get_fetcher()
    
    data = {}
    
    # 指数
    try:
        idx = fetcher.get_index_realtime(['000001', '399001', '399006', '000300', '000016'])
        if len(idx) > 0:
            data['indices'] = idx.to_dict(orient='records')
    except Exception as e:
        print(f'[WARN] indices: {e}')
    
    # 涨停
    try:
        lu = fetcher.get_limit_up(limit=200)
        data['limit_up_count'] = len(lu)
        data['limit_up_top20'] = lu.head(20).to_dict(orient='records') if len(lu) > 0 else []
    except Exception as e:
        print(f'[WARN] limit_up: {e}')
    
    # 跌停
    try:
        ld = fetcher.get_limit_down(limit=100)
        data['limit_down_count'] = len(ld)
        data['limit_down_top10'] = ld.head(10).to_dict(orient='records') if len(ld) > 0 else []
    except Exception as e:
        print(f'[WARN] limit_down: {e}')
    
    # 板块
    try:
        sec = fetcher.get_sector_ranking(top_n=15)
        data['sectors_top'] = sec.head(10).to_dict(orient='records') if len(sec) > 0 else []
        # 跌幅榜排除涨幅榜前10, 避免两个列表重叠
        data['sectors_bottom'] = sec.drop(sec.head(10).index).tail(5).to_dict(orient='records') if len(sec) > 10 else []
    except Exception as e:
        print(f'[WARN] sectors: {e}')
    
    # 主力资金
    try:
        mf = fetcher.get_money_flow()
        data['money_flow_top10'] = mf.head(10).to_dict(orient='records') if len(mf) > 0 else []
    except Exception as e:
        print(f'[WARN] money_flow: {e}')
    
    data['snapshot_time'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(os.path.join(OUT, 'live.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(data, f, default=str)
    print(f'[OK] live.json: snapshot at {data["snapshot_time"]}')


# === 8. 外围市场数据 ===
def gen_overseas_data():
    """生成外围市场数据"""
    from src.data_loader import DataLoader
    loader = DataLoader()
    overview = loader.get_global_overview()
    
    if not overview:
        print('[SKIP] overseas.json: 外围数据不可用')
        return
    
    data = {
        'markets': {},
        'snapshot_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    for name, info in overview.items():
        data['markets'][name] = {
            'close': info.get('close'),
            'chg_pct': info.get('chg_pct'),
            'date': info.get('date', ''),
            'note': info.get('note', ''),
        }
    
    # 综合判断: 美股(隔夜最直接) + 日经/韩国(亚太联动) + 恒生(A+H)
    W = {'标普500': 0.35, '纳斯达克': 0.15, '日经225': 0.20,
         '韩国KOSPI': 0.15, '恒生指数': 0.15}
    total, wsum = 0.0, 0.0
    for name, w in W.items():
        c = overview.get(name, {}).get('chg_pct')
        if c is not None:
            total += c * w
            wsum += w
    total = total / wsum if wsum > 0 else 0.0

    if total > 0.5:
        data['verdict'] = '外围偏强 → A股次日可能高开'
        data['verdict_type'] = 'bullish'
    elif total < -0.5:
        data['verdict'] = '外围偏弱 → A股次日可能低开，注意风险'
        data['verdict_type'] = 'bearish'
    else:
        data['verdict'] = '外围中性 → A股走自身逻辑'
        data['verdict_type'] = 'neutral'

    data['composite_score'] = round(total, 2)
    
    with open(os.path.join(OUT, 'overseas.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(data, f, default=str)
    print(f'[OK] overseas.json: {len(data["markets"])} markets, verdict={data["verdict_type"]}')


# === 9. 交易信号数据 ===
def gen_signals_data():
    """生成交易信号数据"""
    sig_path = os.path.join(DATA, 'latest_signals.csv')
    if not os.path.exists(sig_path):
        print('[SKIP] signals.json: 无信号文件，请先运行 python main.py signal')
        return
    
    df = pd.read_csv(sig_path, encoding='utf-8-sig')
    data = {
        'columns': df.columns.tolist(),
        'rows': df.values.tolist(),
        'count': len(df),
        'buy_count': int(len(df[df['signal'] > 0])) if 'signal' in df.columns else 0,
        'sell_count': int(len(df[df['signal'] < 0])) if 'signal' in df.columns else 0,
        'snapshot_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    with open(os.path.join(OUT, 'signals.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(data, f, default=str)
    print(f'[OK] signals.json: {len(df)} signals')


# === 10. 因子分析数据 ===
def gen_factors_data():
    """生成因子分析数据"""
    icir_path = os.path.join(DATA, 'factor_icir.csv')
    quantile_path = os.path.join(DATA, 'factor_quantile.csv')
    
    data = {'icir': [], 'quantile': [], 'factor_list': []}
    
    if os.path.exists(icir_path):
        df = pd.read_csv(icir_path, encoding='utf-8-sig')
        data['icir'] = df.to_dict(orient='records')
        data['factor_list'] = df['因子'].unique().tolist()
    
    if os.path.exists(quantile_path):
        df = pd.read_csv(quantile_path, encoding='utf-8-sig')
        data['quantile'] = df.to_dict(orient='records')
    
    with open(os.path.join(OUT, 'factors.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(data, f, default=str)
    print(f'[OK] factors.json: {len(data["factor_list"])} factors, {len(data["icir"])} IC records')


# === 11. 毛选原则数据 ===
def gen_principles_data():
    """生成毛选原则映射数据"""
    from src.utils.mao_principles import MILITARY_PRINCIPLES
    
    data = {
        'principles': [],
        'intro': '毛选思想体系 - 量化交易的方法论基础',
    }
    
    for name, info in MILITARY_PRINCIPLES.items():
        data['principles'].append({
            'name': name,
            'principle': info['原则'],
            'implementations': info['量化落地'],
            'code_module': info['代码模块'],
        })
    
    with open(os.path.join(OUT, 'principles.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(data, f, default=str)
    print(f'[OK] principles.json: {len(data["principles"])} principles')


# === 12. 股票池数据 ===
def gen_pool_data():
    """生成股票池摘要数据"""
    pool_path = os.path.join(DATA, 'stock_pool.csv')
    if not os.path.exists(pool_path):
        print('[SKIP] pool.json: 无股票池')
        return
    
    df = pd.read_csv(pool_path, encoding='utf-8-sig')
    df['code'] = df['code'].astype(str).str.zfill(6)
    
    data = {
        'total': len(df),
        'top50': df.head(50).to_dict(orient='records'),
        'snapshot_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    with open(os.path.join(OUT, 'pool.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(data, f, default=str)
    print(f'[OK] pool.json: {len(df)} stocks')


# === 主入口 ===
def gen_daily_data():
    """生成每日决策数据(环境+主线行业+龙头+持仓建议+连板天梯+涨停统计)"""
    from src.daily_assistant import daily_report
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        res = daily_report()
    if not res:
        print('[SKIP] daily.json: 数据不足')
        return

    # 环境
    env = res['env']
    from src.utils.market_env import ENV_DESC, ENV_EXPOSURE
    heat_rows = []
    for ind, r in res.get('heat', []):
        heat_rows.append({'industry': ind, 'zt': int(r['zt']), 'lb': int(r['lb']),
                          'heat': int(r['热度'])})
    leaders = res['leaders']
    lead_rows = [{'industry': r['industry'], 'code': r['code'], 'name': r['name']}
                 for _, r in leaders.iterrows()] if len(leaders) else []

    data = {
        'env': env,
        'env_desc': ENV_DESC.get(env, ''),
        'exposure_pct': int(ENV_EXPOSURE.get(env, 0) * 100),
        'industries': res.get('industries', []),
        'industry_heat': heat_rows,
        'leaders': lead_rows,
        'why': res.get('why', ''),
        'snapshot_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    # === 连板天梯 + 涨停统计 + 龙头实时报价(交易视图数据) ===
    try:
        from src.data_loader import DataLoader
        loader = DataLoader()
        zt = pd.read_csv(os.path.join(DATA, 'zt_events.csv'), header=None,
                         names=['date', 'code', 'lianban'], dtype={'code': str})
        zt['code'] = zt['code'].str.zfill(6)
        zt['date'] = pd.to_datetime(zt['date'])
        latest = zt['date'].max()
        prev_dates = sorted(zt['date'].unique())
        prev_dt = prev_dates[-2] if len(prev_dates) >= 2 else None

        # 名称映射(全市场)
        ind = loader.get_industry()[['code_std', 'code_name', 'industry']].copy()
        ind['std'] = ind['code_std'].astype(str).str.zfill(6)
        name_map = dict(zip(ind['std'], ind['code_name']))
        ind_map = dict(zip(ind['std'], ind['industry']))

        def quote(code):
            """最新收盘/涨跌幅/5日涨幅(来自日线缓存)"""
            df = loader.load_cache(code)
            if df is None or len(df) < 6:
                return None, None, None
            closes = df['close'].tail(6).values
            chg = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] else None
            chg5 = (closes[-1] / closes[0] - 1) * 100 if closes[0] else None
            return round(float(closes[-1]), 2), round(chg, 2) if chg is not None else None, \
                round(chg5, 2) if chg5 is not None else None

        # 连板天梯(当日连板≥2, 按板数降序)
        today = zt[zt['date'] == latest]
        lad = today[today['lianban'] >= 2].sort_values('lianban', ascending=False).head(15)
        ladder = []
        for _, r in lad.iterrows():
            close, chg, chg5 = quote(r['code'])
            ladder.append({'lianban': int(r['lianban']), 'code': r['code'],
                           'name': name_map.get(r['code'], ''),
                           'industry': (ind_map.get(r['code']) or '')[:12],
                           'close': close, 'chg_pct': chg, 'chg5_pct': chg5})
        data['ladder'] = ladder
        data['ladder_date'] = str(latest.date())

        # 涨停统计(今vs昨)
        data['stats'] = {
            'date': str(latest.date()),
            'zt_today': int(len(today)),
            'zt_prev': int(len(zt[zt['date'] == prev_dt])) if prev_dt is not None else None,
            'max_lb': int(today['lianban'].max()) if len(today) else 0,
            'lb2_today': int((today['lianban'] == 2).sum()),
            'lb3p_today': int((today['lianban'] >= 3).sum()),
        }

        # 龙头候选报价
        for l in lead_rows:
            close, chg, chg5 = quote(l['code'])
            l['close'] = close; l['chg_pct'] = chg; l['chg5_pct'] = chg5
    except Exception as e:
        print(f'[WARN] 交易视图数据: {e}')

    # === 策略模拟持仓回放(持仓 + 交易记录) ===
    try:
        from src.backtest.portfolio_tracker import replay
        port = replay(save_json_path=os.path.join(OUT, 'portfolio.json'))
        data['portfolio'] = {
            'as_of': port['as_of'],
            'total_ret_pct': port['total_ret_pct'],
            'max_dd_pct': port['max_dd_pct'],
            'n_holdings': port['n_holdings'],
            'n_trades': port['n_trades'],
            'holdings': port['holdings'][:20],
            'trades': port['trades'][:30],
        }
    except Exception as e:
        print(f'[WARN] 模拟持仓: {e}')

    with open(os.path.join(OUT, 'daily.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(data, f, default=str)
    print(f'[OK] daily.json: 环境{env}, {len(heat_rows)}主线行业, '
          f'天梯{len(data.get("ladder", []))}只')


def main():
    print('=== 生成全量前端数据包 ===\n')

    # 基础数据包（sentiment/monthly/markers/backtest/trades/walkforward/yearly）
    try:
        generate_base_data()
    except Exception as e:
        print(f'[ERR] 基础数据包: {e}')

    # 新增模块
    print('\n--- 新增模块 ---')
    try:
        gen_regime_data()
    except Exception as e:
        print(f'[ERR] regime: {e}')
    
    try:
        gen_live_data()
    except Exception as e:
        print(f'[ERR] live: {e}')
    
    try:
        gen_overseas_data()
    except Exception as e:
        print(f'[ERR] overseas: {e}')
    
    try:
        gen_signals_data()
    except Exception as e:
        print(f'[ERR] signals: {e}')
    
    try:
        gen_factors_data()
    except Exception as e:
        print(f'[ERR] factors: {e}')
    
    try:
        gen_principles_data()
    except Exception as e:
        print(f'[ERR] principles: {e}')

    try:
        gen_daily_data()
    except Exception as e:
        print(f'[ERR] daily: {e}')
    
    try:
        gen_pool_data()
    except Exception as e:
        print(f'[ERR] pool: {e}')
    
    print('\n[DONE] 全量数据包生成完成')


if __name__ == '__main__':
    main()
