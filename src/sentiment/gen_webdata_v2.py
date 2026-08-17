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

# NaN/Inf 安全的 JSON 序列化
SafeJSONEncoder = type(json.JSONEncoder)('SafeJSONEncoder', (json.JSONEncoder,), {
    'default': staticmethod(lambda o: None if (isinstance(o, float) and (math.isnan(o) or math.isinf(o))) else str(o))
})
_safe_dump = json.dump
def json_dump_safe(obj, f, **kwargs):
    kwargs.setdefault('ensure_ascii', False)
    _safe_dump(obj, f, cls=SafeJSONEncoder, **kwargs)
json.dump = json_dump_safe

# 先运行原始 gen_webdata 的逻辑
sys.path.insert(0, ROOT)
from src.sentiment.gen_webdata import *  # noqa — 这会执行原始数据生成


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
        json.dump(regime_data, f, ensure_ascii=False, default=str)
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
        data['sectors_bottom'] = sec.tail(5).to_dict(orient='records') if len(sec) > 5 else []
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
        json.dump(data, f, ensure_ascii=False, default=str)
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
    
    # 综合判断
    us_chg = overview.get('标普500', {}).get('chg_pct', 0) or 0
    hk_chg = overview.get('恒生指数', {}).get('chg_pct', 0) or 0
    total = (us_chg + hk_chg) / 2
    
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
        json.dump(data, f, ensure_ascii=False, default=str)
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
        json.dump(data, f, ensure_ascii=False, default=str)
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
        json.dump(data, f, ensure_ascii=False, default=str)
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
        json.dump(data, f, ensure_ascii=False, default=str)
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
        json.dump(data, f, ensure_ascii=False, default=str)
    print(f'[OK] pool.json: {len(df)} stocks')


# === 主入口 ===
def main():
    print('=== 生成全量前端数据包 ===\n')
    
    # 原始数据包（sentiment/monthly/markers/backtest/trades/walkforward/yearly）
    # 已由 gen_webdata.py 模块级代码生成
    
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
        gen_pool_data()
    except Exception as e:
        print(f'[ERR] pool: {e}')
    
    print('\n[DONE] 全量数据包生成完成')


if __name__ == '__main__':
    main()
