"""
量价因子模块
包含: 动量、反转、波动率、换手率、量价背离
"""
import pandas as pd
import numpy as np
from src.factors.base import FactorBase


class Momentum(FactorBase):
    """动量因子 - 过去N日收益率"""

    def __init__(self, period=20):
        super().__init__(f"momentum_{period}")
        self.period = period

    def calculate(self, df):
        close = df['close']
        return close.pct_change(self.period)


class Reversal(FactorBase):
    """反转因子 - 过去N日收益率取反（跌多了会反弹）"""

    def __init__(self, period=5):
        super().__init__(f"reversal_{period}")
        self.period = period

    def calculate(self, df):
        close = df['close']
        return -close.pct_change(self.period)


class Volatility(FactorBase):
    """波动率因子 - 过去N日收益率标准差"""

    def __init__(self, period=20):
        super().__init__(f"volatility_{period}")
        self.period = period

    def calculate(self, df):
        ret = df['close'].pct_change()
        return ret.rolling(self.period).std()


class Turnover(FactorBase):
    """换手率因子 - 过去N日平均换手率"""

    def __init__(self, period=5):
        super().__init__(f"turnover_avg_{period}")
        self.period = period

    def calculate(self, df):
        if 'turnover' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df['turnover'].rolling(self.period).mean()


class VolumePriceDivergence(FactorBase):
    """量价背离因子 - 价涨量缩为背离信号"""

    def __init__(self, period=10):
        super().__init__(f"vol_price_div_{period}")
        self.period = period

    def calculate(self, df):
        price_chg = df['close'].pct_change(self.period)
        volume_chg = df['volume'].pct_change(self.period)
        # 价涨量缩 → 正值（背离）
        return price_chg - volume_chg / (volume_chg.abs() + 1) * price_chg


class MAAlign(FactorBase):
    """均线排列因子 - 均线多头排列程度"""

    def __init__(self, short=5, mid=20, long=60):
        super().__init__(f"ma_align_{short}_{mid}_{long}")
        self.short = short
        self.mid = mid
        self.long = long

    def calculate(self, df):
        close = df['close']
        ma_s = close.rolling(self.short).mean()
        ma_m = close.rolling(self.mid).mean()
        ma_l = close.rolling(self.long).mean()

        # 多头排列: ma_s > ma_m > ma_l → 正值
        align = np.where(
            (ma_s > ma_m) & (ma_m > ma_l), 1,
            np.where((ma_s < ma_m) & (ma_m < ma_l), -1, 0)
        )
        return pd.Series(align, index=df.index)


class AmihudIlliquidity(FactorBase):
    """Amihud非流动性因子 - |收益率|/成交额"""

    def __init__(self, period=20):
        super().__init__(f"amihud_{period}")
        self.period = period

    def calculate(self, df):
        ret = df['close'].pct_change().abs()
        amount = df['amount'].replace(0, np.nan)
        amihud = ret / amount * 1e9
        return amihud.rolling(self.period).mean()
