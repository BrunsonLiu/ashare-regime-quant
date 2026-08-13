"""
情绪因子模块
包含: 涨停连板、换手率异动、市场宽度
"""
import pandas as pd
import numpy as np
from src.factors.base import FactorBase


class LimitUpCount(FactorBase):
    """涨停连板数因子"""

    def __init__(self):
        super().__init__("limit_up_count")

    def calculate(self, df):
        # A股涨停10%（主板）或20%（创业板/科创板）
        pct = df['close'].pct_change()
        code = df['code'].iloc[0] if 'code' in df.columns else ''

        if str(code).startswith('30') or str(code).startswith('68'):
            limit_pct = 0.19  # 20%涨停（留余量）
        else:
            limit_pct = 0.095  # 10%涨停

        is_limit = pct >= limit_pct

        # 计算连续涨停天数
        count = 0
        counts = []
        for v in is_limit:
            if v:
                count += 1
            else:
                count = 0
            counts.append(count)

        return pd.Series(counts, index=df.index)


class TurnoverSpike(FactorBase):
    """换手率异动因子 - 当前换手率偏离均值的程度"""

    def __init__(self, period=20):
        super().__init__(f"turnover_spike_{period}")
        self.period = period

    def calculate(self, df):
        if 'turnover' not in df.columns:
            return pd.Series(np.nan, index=df.index)

        avg = df['turnover'].rolling(self.period).mean()
        std = df['turnover'].rolling(self.period).std()
        return (df['turnover'] - avg) / (std + 1e-8)


class PriceGap(FactorBase):
    """跳空缺口因子"""

    def __init__(self):
        super().__init__("price_gap")

    def calculate(self, df):
        gap = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
        return gap
