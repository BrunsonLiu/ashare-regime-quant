# -*- coding: utf-8 -*-
"""
测试公共辅助:
- 项目根目录加入 sys.path
- akshare/baostock 未安装时注入空 stub(测试不依赖网络与可选依赖)
- 合成行情数据构造器
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 条件 stub: 已安装则用真实库, 未安装才注入 —— 保证有网/无网环境都能跑
for _name in ('akshare', 'baostock'):
    try:
        __import__(_name)
    except ImportError:
        _stub = types.ModuleType(_name)
        _stub.login = lambda *a, **k: None
        _stub.logout = lambda *a, **k: None
        sys.modules[_name] = _stub

import pandas as pd
import numpy as np


def make_stock_df(n=150, base=10.0, seed=1, code='600001'):
    """标准合成日线: 几何随机游走 + OHLC 包络 + pctChg"""
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0003, 0.015, n)
    close = base * np.cumprod(1 + ret)
    open_ = close * (1 + rng.normal(0, 0.005, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, n)))
    df = pd.DataFrame({
        'date': pd.bdate_range('2025-01-01', periods=n),
        'open': open_, 'high': high, 'low': low, 'close': close,
        'volume': rng.uniform(1e6, 5e6, n),
        'amount': rng.uniform(1e7, 5e7, n),
    })
    if code:
        df['code'] = code
    df['pctChg'] = df['close'].pct_change().fillna(0) * 100
    return df


def make_index_df(n=150, start=3000.0):
    """合成指数: 缓慢上行"""
    closes = start + np.arange(n) * 2.0
    return pd.DataFrame({
        'date': pd.bdate_range('2025-01-01', periods=n),
        'open': closes - 5, 'high': closes + 10, 'low': closes - 10,
        'close': closes, 'volume': 1e8, 'amount': 1e10, 'pctChg': 0.5,
    })
