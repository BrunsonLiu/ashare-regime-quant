# -*- coding: utf-8 -*-
"""
时序契约测试 —— 自动抓"前视偏差 / 未来函数"
================================================
思路(比人工自查一百遍有效):
  在时点 T 做决策, 只允许读 **≤T** 的数据。
  若把 T **之后**的行情替换成完全不同的噪声, 决策结果仍必须**逐字相同**;
  一旦不同 → 该函数偷看了未来(前视)。

本文件对生产链路里的核心决策函数逐一施加"未来扰动":
  - _industry_score   (选行业打分)
  - _mktcap_at        (时点市值)
  - analyze           (结构画像 力量/位置/博弈/节奏)
  - select_stocks     (选龙头, 含结构关)
另外守护两条"确定性契约":
  - backtest 同一输入跑两次结果一致(防 set 遍历随机化)

历史教训(这些契约就是为了防它们复发):
  · guardian 回测曾用当日收盘选股却按当日开盘成交(前视, commit 1473177)
  · guardian.backtest 曾遍历 set(targets) → 回测不可复现(commit 546e0ab)
"""
import os
import sys

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402  (加入项目根 + 合成行情工厂)
make_stock_df, make_index_df = helpers.make_stock_df, helpers.make_index_df


# ==================== 未来扰动的构造 ====================

def _corrupt_after(df, asof, seed=999):
    """把 df 中 **严格晚于 asof** 的所有行情列替换成剧烈不同的噪声。

    返回新 df(不改原 df)。价格乘上 0.2~5 的随机因子, 量能乘 0.01~100,
    使"用了未来数据"的函数必然给出不同答案。
    """
    d = df.copy()
    asof = pd.Timestamp(asof)
    date_col = 'date' if 'date' in d.columns else d.index.name
    if 'date' in d.columns:
        mask = pd.to_datetime(d['date']) > asof
    else:
        mask = d.index > asof
    rng = np.random.default_rng(seed)
    n_future = int(mask.sum())
    if n_future == 0:
        return d
    for col in ('open', 'high', 'low', 'close'):
        if col in d.columns:
            f = rng.uniform(0.2, 5.0, n_future)
            d.loc[mask, col] = d.loc[mask, col].values * f
    for col in ('volume', 'amount'):
        if col in d.columns:
            d.loc[mask, col] = d.loc[mask, col].values * rng.uniform(0.01, 100.0, n_future)
    return d


def _as_index(df):
    """date 列 → DatetimeIndex(部分决策函数按 index 切片)。"""
    d = df.copy()
    d['date'] = pd.to_datetime(d['date'])
    return d.set_index('date')


# ==================== 契约 1: 选行业打分 ====================

class TestIndustryScoreTiming:
    def _long_industry(self, n=900, seed=3):
        """构造长度足够(>750)的行业指数。"""
        rng = np.random.default_rng(seed)
        close = 1000 * np.cumprod(1 + rng.normal(0.0005, 0.012, n))
        return pd.DataFrame({
            'date': pd.bdate_range('2022-01-01', periods=n),
            'open': close * 0.999, 'high': close * 1.01,
            'low': close * 0.99, 'close': close,
        }).set_index('date')

    def test_score_unchanged_by_future(self):
        from src.strategy.guardian import _industry_score
        idx = self._long_industry()
        asof = idx.index[600]                      # 决策时点(留 ~300 天未来)
        base = _industry_score(idx, asof)
        assert base is not None, '样本太短, 打分返回 None'
        # 扰动所有 >asof 的数据
        idx2 = _corrupt_after(idx.reset_index(), asof, seed=7).set_index('date')
        after = _industry_score(idx2, asof)
        assert after == base, (
            f'选行业打分受未来数据影响 → 前视!\n asof={asof.date()}\n'
            f' 原={base}\n 扰动未来后={after}')

    def test_tsummary_uses_only_past_len(self):
        """截断到 asof 与"扰动未来"必须给同一结果(等价性)。"""
        from src.strategy.guardian import _industry_score
        idx = self._long_industry()
        asof = idx.index[600]
        truncated = idx[idx.index <= asof]
        a = _industry_score(truncated, asof)
        b = _industry_score(idx, asof)
        assert a == b, '截断与扰动结果不一致 → 存在对未来的依赖'


# ==================== 契约 2: 时点市值 ====================

class TestMktcapTiming:
    def _stock(self, n=400, seed=11, code='600001'):
        df = make_stock_df(n=n, seed=seed, code=code)
        df['outstanding_share'] = 1e9
        return _as_index(df)

    def test_mktcap_unchanged_by_future(self):
        from src.strategy.guardian import _mktcap_at
        df = self._stock()
        asof = df.index[300]
        base = _mktcap_at(df, asof)
        assert base is not None
        df2 = _corrupt_after(df.reset_index(), asof, seed=13).set_index('date')
        after = _mktcap_at(df2, asof)
        assert after == base, f'时点市值受未来影响 → 前视! 原={base} 后={after}'


# ==================== 契约 3: 结构画像 ====================

class TestStructureTiming:
    def test_analyze_unchanged_by_future(self):
        from src.utils.market_structure import analyze
        df = make_stock_df(n=400, seed=21, code='600002')
        asof = pd.Timestamp(df['date'].iloc[300])
        base = analyze(df.copy(), asof)
        assert base is not None and '否决' in base
        df2 = _corrupt_after(df, asof, seed=23)
        after = analyze(df2, asof)
        # 逐键比对(除个别数值型可能含浮点, 用 == 也可: 未来被完全替换)
        assert after is not None
        diff = {k: (base[k], after[k]) for k in base if base[k] != after.get(k)}
        assert not diff, f'结构画像受未来数据影响 → 前视! 差异: {diff}'

    def test_structure_veto_only_past(self):
        """结构关的'否决'标记不得依赖未来。"""
        from src.utils.market_structure import analyze
        df = make_stock_df(n=400, seed=31, code='600003')
        asof = pd.Timestamp(df['date'].iloc[300])
        b = analyze(df.copy(), asof)
        a = analyze(_corrupt_after(df, asof, seed=33), asof)
        assert b['否决'] == a['否决'], '结构关否决标记受未来影响 → 前视'


# ==================== 契约 4: 选龙头(含结构关) ====================

class TestSelectStocksTiming:
    def _universe(self):
        data = {}
        ths = {}
        for i in range(6):
            code = f'60000{i}'
            df = make_stock_df(n=400, seed=100 + i, code=code)
            df['outstanding_share'] = (1e9 * (i + 1))   # 市值递增
            data[code] = _as_index(df)
            ths[code] = '半导体'
        return data, ths

    def test_select_unchanged_by_future(self):
        from src.strategy.guardian import select_stocks
        data, ths = self._universe()
        asof = list(data.values())[0].index[300]
        base = select_stocks(['半导体'], data, ths, asof=asof, use_structure=True)
        data2 = {c: _corrupt_after(d.reset_index(), asof, seed=41 + i).set_index('date')
                 for i, (c, d) in enumerate(data.items())}
        after = select_stocks(['半导体'], data2, ths, asof=asof, use_structure=True)
        assert after == base, f'选龙头受未来影响 → 前视! 原={base} 后={after}'


# ==================== 契约 5: 回测确定性 ====================

class TestBacktestDeterminism:
    """确定性必须在**不同进程**间成立 —— Python set/str 的遍历顺序随
    PYTHONHASHSEED 变化, 同进程内两次比较抓不到该 bug(真实教训: commit 546e0ab)。
    故用不同 PYTHONHASHSEED 起子进程, 比较回测结果。"""

    _SCRIPT = r'''
import os, sys, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), 'tests'))
import helpers
import pandas as pd
import src.strategy.guardian as G

data, ths = {}, {}
CODES = []
for i in range(12):
    code = f'60010{i}'
    CODES.append(code)
    df = helpers.make_stock_df(n=500, seed=200 + i, code=code)
    df['outstanding_share'] = 1e9 * (i + 1)
    d = df.copy(); d['date'] = pd.to_datetime(d['date'])
    data[code] = d.set_index('date')[['open','high','low','close','volume']]
    ths[code] = ['半导体','白酒','电池','煤炭'][i % 4]

# 直接给定行业/标的: 绕开磁盘文件(合成码不在真实同花顺映射里)
G.select_industries = lambda *a, **k: ['半导体','白酒','电池','煤炭']
G.select_stocks = lambda inds, data, ths_map, asof=None, **k: list(CODES)

gate = pd.Series(True, index=pd.bdate_range('2025-01-01', periods=500))
r = G.backtest(data, ths, gate, use_structure=False, require_position=False)
print(json.dumps({'ret': r['ret'], 'trades': r['trades'],
                  'eq_last': round(float(r['eq'].iloc[-1]), 6)}))
'''

    def _run(self, hashseed):
        import subprocess
        env = dict(os.environ, PYTHONHASHSEED=str(hashseed))
        out = subprocess.run([sys.executable, '-c', self._SCRIPT],
                             capture_output=True, text=True, env=env, timeout=300)
        assert out.returncode == 0, f'subprocess failed: {out.stderr[-800:]}'
        import json
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_identical_across_hash_seeds(self):
        a = self._run(0)
        b = self._run(1)
        c = self._run(12345)
        assert a == b == c, (
            f'回测随 PYTHONHASHSEED 变化 → 不可复现(set遍历随机化)!\n'
            f' seed0={a}\n seed1={b}\n seed12345={c}')

