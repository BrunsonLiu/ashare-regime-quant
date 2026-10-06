# -*- coding: utf-8 -*-
"""
生成前端可视化数据包 JSON
从 sentiment_3y.csv + backtest 数据 生成前端所需的全部数据

注意: 全部生成逻辑在 generate() 中, import 本模块不会产生副作用;
      main.py 的 gen-webdata 命令经由 gen_webdata_v2.main() 调用 generate()。
"""
import json, os, sys, math
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'web', 'data')

os.makedirs(OUT, exist_ok=True)


def sanitize_json(obj):
    """递归把 NaN/Inf 浮点转成 None —— json 对 float 是原生编码,
    default 钩子拦不住 NaN, 而 NaN 字面量不是合法 JSON, 浏览器 JSON.parse 直接报错。
    numpy 整数同时转成原生 int(json 无法直接序列化 np.int64)。"""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, np.floating):
        return None if (np.isnan(obj) or np.isinf(obj)) else float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_json(v) for v in obj]
    return obj


def json_dump_safe(obj, f, **kwargs):
    """NaN 安全 + allow_nan=False 兜底(残留 NaN 直接报错而不是写出非法 JSON)"""
    kwargs.setdefault('ensure_ascii', False)
    json.dump(sanitize_json(obj), f, allow_nan=False, **kwargs)


def generate():
    """生成 sentiment/monthly/markers/backtest/trades/walkforward/yearly 七个数据包"""
    # === 1. 情绪数据 ===
    s = pd.read_csv(os.path.join(DATA, 'sentiment_3y.csv'), parse_dates=['date'])
    s = s.sort_values('date').reset_index(drop=True)

    # 分位数
    quantiles = {
        'zt_count': {'p10': int(s.zt_count.quantile(0.1)), 'p20': int(s.zt_count.quantile(0.2)),
                     'p50': int(s.zt_count.quantile(0.5)), 'p80': int(s.zt_count.quantile(0.8)), 'p90': int(s.zt_count.quantile(0.9))},
        'zhaban_rate': {'p10': round(s.zhaban_rate.quantile(0.1),4), 'p20': round(s.zhaban_rate.quantile(0.2),4),
                        'p50': round(s.zhaban_rate.quantile(0.5),4), 'p80': round(s.zhaban_rate.quantile(0.8),4), 'p90': round(s.zhaban_rate.quantile(0.9),4)},
        'lianban_height': {'p80': int(s.lianban_height.quantile(0.8)), 'p90': int(s.lianban_height.quantile(0.9))},
    }

    sentiment_data = {
        'dates': s.date.dt.strftime('%Y-%m-%d').tolist(),
        'zt_count': s.zt_count.tolist(),
        'zhaban_count': s.zhaban_count.tolist(),
        'zhaban_rate': s.zhaban_rate.tolist(),
        'lianban_height': s.lianban_height.tolist(),
        'lianban2': s.lianban2.tolist(),
        'lianban3': s.lianban3.tolist(),
        'lianban4p': s.lianban4p.tolist(),
        'shouban': s.shouban.tolist(),
        'shouban_ratio': s.shouban_ratio.tolist(),
        'quantiles': quantiles,
        'stats': {
            'total_days': len(s),
            'date_start': s.date.min().strftime('%Y-%m-%d'),
            'date_end': s.date.max().strftime('%Y-%m-%d'),
            'zt_mean': round(s.zt_count.mean(), 1),
            'zt_median': float(s.zt_count.median()),
            'zhaban_mean': round(s.zhaban_rate.mean(), 4),
            'lb_mean': round(s.lianban_height.mean(), 1),
        }
    }

    with open(os.path.join(OUT, 'sentiment.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(sentiment_data, f)
    print(f'[OK] sentiment.json: {len(s)} days')

    # === 2. 月度热力图 ===
    s['ym'] = s.date.dt.to_period('M').astype(str)
    monthly = s.groupby('ym').agg(
        zt_mean=('zt_count', 'mean'),
        zhaban_mean=('zhaban_rate', 'mean'),
        lb_mean=('lianban_height', 'mean'),
        days=('date', 'count'),
        bing_days=('zt_count', lambda x: int((x < quantiles['zt_count']['p20']).sum())),
    ).reset_index()

    monthly_data = {
        'months': monthly.ym.tolist(),
        'zt_mean': [round(x, 1) for x in monthly.zt_mean],
        'zhaban_mean': [round(x, 4) for x in monthly.zhaban_mean],
        'lb_mean': [round(x, 1) for x in monthly.lb_mean],
        'bing_days': monthly.bing_days.tolist(),
    }
    with open(os.path.join(OUT, 'monthly.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(monthly_data, f)
    print(f'[OK] monthly.json: {len(monthly)} months')

    # === 3. 冰点/高潮标记 ===
    zt_p20 = quantiles['zt_count']['p20']
    zh_p80 = quantiles['zhaban_rate']['p80']
    zt_p80 = quantiles['zt_count']['p80']

    s['is_bing'] = ((s.zt_count < zt_p20) | (s.zhaban_rate > zh_p80)).astype(int)
    s['is_gao'] = (s.zt_count > zt_p80).astype(int)

    # 冰点反转统计
    bing_idx = s.index[s.is_bing == 1].tolist()
    reversal_stats = {'total_bing': len(bing_idx), 'rev_3d': 0, 'rev_5d': 0, 'avg_3d': 0, 'avg_5d': 0}
    rev_3d_list = []
    rev_5d_list = []
    for idx in bing_idx:
        if idx + 3 < len(s):
            ret_3d = s.iloc[idx+3].zt_count - s.iloc[idx].zt_count
            rev_3d_list.append(ret_3d)
            if ret_3d > 0:
                reversal_stats['rev_3d'] += 1
        if idx + 5 < len(s):
            ret_5d = s.iloc[idx+5].zt_count - s.iloc[idx].zt_count
            rev_5d_list.append(ret_5d)
            if ret_5d > 0:
                reversal_stats['rev_5d'] += 1

    reversal_stats['rev_3d_rate'] = round(reversal_stats['rev_3d'] / max(len(rev_3d_list), 1), 4)
    reversal_stats['rev_5d_rate'] = round(reversal_stats['rev_5d'] / max(len(rev_5d_list), 1), 4)
    reversal_stats['avg_3d'] = round(np.mean(rev_3d_list), 1) if rev_3d_list else 0
    reversal_stats['avg_5d'] = round(np.mean(rev_5d_list), 1) if rev_5d_list else 0

    markers = {
        'bing_days': s[s.is_bing == 1].date.dt.strftime('%Y-%m-%d').tolist(),
        'gao_days': s[s.is_gao == 1].date.dt.strftime('%Y-%m-%d').tolist(),
        'reversal_stats': reversal_stats,
        'thresholds': {'zt_p20': zt_p20, 'zt_p80': zt_p80, 'zh_p80': zh_p80},
    }
    with open(os.path.join(OUT, 'markers.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(markers, f)
    print(f'[OK] markers.json: {len(bing_idx)} bing days, {reversal_stats["rev_3d_rate"]*100:.0f}% 3d reversal')

    # === 4. 回测数据 ===
    eq_path = os.path.join(DATA, 'backtest_equity.csv')
    tr_path = os.path.join(DATA, 'backtest_trades.csv')
    wf_path = os.path.join(DATA, 'walkforward.csv')

    if os.path.exists(eq_path):
        eq = pd.read_csv(eq_path, parse_dates=['date'])
        eq_data = {
            'dates': eq.date.dt.strftime('%Y-%m-%d').tolist(),
            'equity': eq.equity.round(2).tolist(),
            'regime': eq.regime.tolist() if 'regime' in eq.columns else [],
        }
        # 计算回撤
        eq['peak'] = eq.equity.cummax()
        eq['dd'] = (eq.equity / eq.peak - 1) * 100
        eq_data['drawdown'] = eq.dd.round(2).tolist()

        # 统计
        total_ret = (eq.equity.iloc[-1] / eq.equity.iloc[0] - 1) * 100
        max_dd = eq.dd.min()
        eq_data['stats'] = {
            'total_return': round(total_ret, 2),
            'max_drawdown': round(max_dd, 2),
            'final_equity': round(eq.equity.iloc[-1], 0),
            'initial_capital': round(eq.equity.iloc[0], 0),
            'days': len(eq),
        }
        with open(os.path.join(OUT, 'backtest.json'), 'w', encoding='utf-8') as f:
            json_dump_safe(eq_data, f)
        print(f'[OK] backtest.json: {len(eq)} days, ret={total_ret:.1f}%')

    if os.path.exists(tr_path):
        tr = pd.read_csv(tr_path)
        # NaN -> None, 否则 .values.tolist() 会带出 float('nan')
        tr = tr.astype(object).where(pd.notnull(tr), None)
        tr_data = {
            'columns': tr.columns.tolist(),
            'rows': tr.values.tolist(),
        }
        with open(os.path.join(OUT, 'trades.json'), 'w', encoding='utf-8') as f:
            json_dump_safe(tr_data, f)
        print(f'[OK] trades.json: {len(tr)} trades')

    if os.path.exists(wf_path):
        wf = pd.read_csv(wf_path)
        wf = wf.astype(object).where(pd.notnull(wf), None)
        wf_data = wf.to_dict(orient='records')
        with open(os.path.join(OUT, 'walkforward.json'), 'w', encoding='utf-8') as f:
            json_dump_safe(wf_data, f, default=str)
        print(f'[OK] walkforward.json: {len(wf)} segments')

    # === 5. 年度统计 ===
    s['year'] = s.date.dt.year
    yearly = s.groupby('year').agg(
        zt_mean=('zt_count', 'mean'),
        zhaban_mean=('zhaban_rate', 'mean'),
        lb_mean=('lianban_height', 'mean'),
        bing_days=('is_bing', 'sum'),
        days=('date', 'count'),
    ).round(3).reset_index()

    yearly_data = yearly.to_dict(orient='records')
    with open(os.path.join(OUT, 'yearly.json'), 'w', encoding='utf-8') as f:
        json_dump_safe(yearly_data, f, default=str)
    print(f'[OK] yearly.json: {len(yearly)} years')

    print('\n[DONE] 所有数据包已生成到 web/data/')


def main():
    generate()


if __name__ == '__main__':
    main()
