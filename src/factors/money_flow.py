"""
资金面因子模块
包含: 主力净流入、北向资金、龙虎榜
"""
import pandas as pd
import numpy as np
from src.factors.base import FactorBase


class MainMoneyFlow(FactorBase):
    """主力资金净流入因子"""

    def __init__(self, period=5):
        super().__init__(f"main_flow_{period}")
        self.period = period

    def calculate(self, df):
        if 'amount' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        # 简化：用成交额变化趋势近似
        # 后续接入个股资金流数据后替换
        flow = df['amount'].diff(self.period)
        return flow


class NorthHoldingChange(FactorBase):
    """北向资金持股变化因子（需要外部数据）"""

    def __init__(self):
        super().__init__("north_change")

    def calculate(self, df):
        # 北向数据需要单独拉取，这里先占位
        return pd.Series(np.nan, index=df.index)


class AmountRatio(FactorBase):
    """量比因子 - 当日成交量与过去平均的比值"""

    def __init__(self, period=20):
        super().__init__(f"amount_ratio_{period}")
        self.period = period

    def calculate(self, df):
        avg_vol = df['volume'].rolling(self.period).mean().shift(1)
        return df['volume'] / avg_vol


class BigOrderNetInflow(FactorBase):
    """大单净流入因子（需要个股资金流数据）"""

    def __init__(self):
        super().__init__("big_order_net")

    def calculate(self, df):
        # 占位，后续接入资金流数据
        return pd.Series(np.nan, index=df.index)
