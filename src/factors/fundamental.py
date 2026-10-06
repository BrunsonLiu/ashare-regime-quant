"""
基本面因子模块
包含: PE、PB、ROE、营收增速、景气度
"""
import pandas as pd
import numpy as np
from src.factors.base import FactorBase


class PEFactor(FactorBase):
    """市盈率因子 - 越低越便宜（价值投资）"""

    def __init__(self):
        super().__init__("pe")

    def calculate(self, df):
        if 'pe' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df['pe']


class PBFactor(FactorBase):
    """市净率因子"""

    def __init__(self):
        super().__init__("pb")

    def calculate(self, df):
        if 'pb' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df['pb']


class ROEFactor(FactorBase):
    """ROE因子 - 净资产收益率，越高越好"""

    def __init__(self):
        super().__init__("roe")

    def calculate(self, df):
        if 'roe' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df['roe']


class RevenueGrowth(FactorBase):
    """营收增速因子

    注意: 输入是个股日线, pct_change(4) 是近4个交易日的"营收代理序列"变化,
    不是财报同比。接入真实季度财务数据前, 因子语义按短期动量理解。
    """

    def __init__(self):
        super().__init__("revenue_growth")

    def calculate(self, df):
        if 'revenue' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df['revenue'].pct_change(4)


class MarketCap(FactorBase):
    """市值因子 - 小市值效应"""

    def __init__(self):
        super().__init__("market_cap")

    def calculate(self, df):
        if 'total_mv' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df['total_mv']


class ProsperityFactor(FactorBase):
    """
    景气度因子 - 综合评估行业/个股的景气度
    景气度 = 盈利趋势 + 营收代理趋势 + 量价景气

    你说"看景气度"，这个因子就是核心。
    景气度高的股票优先选。
    注意: roe/revenue 列来自日线代理数据, diff(4)/pct_change(4) 是近4个交易日
    变化而非财报同比; 接入真实财务数据后语义自动升级。
    """

    def __init__(self):
        super().__init__("prosperity")

    def calculate(self, df):
        components = []

        # 盈利趋势（ROE变化）
        if 'roe' in df.columns:
            roe_change = df['roe'].diff(4)
            components.append(roe_change)

        # 营收代理增速（日线序列, 非财报同比）
        if 'revenue' in df.columns:
            rev_growth = df['revenue'].pct_change(4)
            components.append(rev_growth)

        # 量价景气度：近期成交额放大 + 价格上行
        if 'amount' in df.columns and 'close' in df.columns:
            amt_ma = df['amount'].rolling(20).mean()
            amt_trend = df['amount'] / amt_ma - 1  # 成交额放大
            price_trend = df['close'].pct_change(20)  # 价格趋势
            price_volume_prosperity = amt_trend * price_trend  # 量价齐升=景气
            components.append(price_volume_prosperity)

        if not components:
            return pd.Series(np.nan, index=df.index)

        # 扩展窗口标准化(每行只用≤t数据): 与"逐日切片再取末行"严格等价,
        # 同时保证因子后视纯(原实现用全样本均值/方差, 是隐性未来函数)
        normalized = []
        for comp in components:
            mean = comp.expanding().mean()
            std = comp.expanding().std()
            z = (comp - mean) / std.replace(0, np.nan)
            normalized.append(z.fillna(0))

        result = sum(normalized) / len(normalized)
        return result


class IndustryRotation(FactorBase):
    """
    行业轮动因子 - 找主线
    你说"找主线"，这个因子追踪行业资金流向趋势

    逻辑：
    - 资金持续流入的行业 = 主线方向
    - 行业内个股受益于行业景气度
    """

    def __init__(self, rotation_window=20):
        super().__init__(f"industry_rotation_{rotation_window}")
        self.rotation_window = rotation_window

    def calculate(self, df):
        if 'amount' not in df.columns:
            return pd.Series(np.nan, index=df.index)

        # 成交额趋势：近期均值 vs 长期均值
        short_ma = df['amount'].rolling(5).mean()
        long_ma = df['amount'].rolling(self.rotation_window).mean()

        # 资金流入趋势
        flow_trend = (short_ma - long_ma) / long_ma.replace(0, np.nan)

        return flow_trend
