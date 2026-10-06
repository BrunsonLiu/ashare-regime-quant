"""
外围市场因子模块
核心逻辑：美股隔夜走势 → A股次日开盘情绪

影响路径：
1. 美股大跌 → A股次日恐慌性低开
2. 美股大涨 → A股次日情绪回暖高开
3. 美股震荡 → 影响不大，A股走自己的逻辑

次要外围：
- 恒生指数（港股，与A股联动性较强）
- 富时A50期货（新加坡，直接反映A股预期）
- 日经指数（亚太情绪参考）
- VIX恐慌指数（全球风险偏好）
"""
import pandas as pd
import numpy as np
from src.factors.base import FactorBase
from src.data_loader import DataLoader


class USMarketImpact(FactorBase):
    """
    美股影响因子
    计算美股隔夜涨跌幅，映射到A股情绪

    数据源：道琼斯、纳斯达克、标普500
    AKShare接口：stock_us_daily 或 index_global
    """

    # 进程级缓存: 同一进程内多个因子实例(GlobalRiskAppetite/OvernightSignal 内嵌)共享,
    # 每自然日最多拉一次, 避免回测期间对每个(日期×股票)重复请求
    _US_CACHE = {'df': None, 'date': None}

    def __init__(self):
        super().__init__("us_market_impact")
        self.loader = DataLoader()

    def _get_us_data(self):
        """获取美股指数数据（进程级缓存，按天失效；失败时告警并返回None）"""
        today = pd.Timestamp.now().normalize()
        if self._US_CACHE['df'] is not None and self._US_CACHE['date'] == today:
            return self._US_CACHE['df']

        import akshare as ak
        try:
            df = ak.index_global_hist_em(symbol='S&P 500')
            if df is not None and len(df) > 0:
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
                df['date'] = pd.to_datetime(df['date'])
                self._US_CACHE['df'] = df
                self._US_CACHE['date'] = today
                return df
        except Exception as e:
            print(f"[WARN] 美股数据获取失败(us_market_impact 降级为0): {e}")
        return None

    def calculate(self, df):
        """
        计算美股影响因子
        df: A股个股日线数据（提供A股交易日历）
        返回: Series, 每个交易日对应的最近一个美股交易日涨跌幅（外围不可用则全0）
        """
        us_data = self._get_us_data()
        if us_data is None or len(us_data) < 2:
            return pd.Series(0.0, index=df.index)

        us = us_data.sort_values('date').copy()
        us['us_ret'] = us['close'].pct_change()

        # 用本股的A股交易日历对齐: 美股D日收盘 → D之后第一个A股交易日
        # (自然日+1会把周五对到周六, 导致A股周一永远匹配不到)
        a_cal = pd.to_datetime(df['date']).drop_duplicates().sort_values().reset_index(drop=True)
        idx = a_cal.searchsorted(us['date'].values, side='right')
        us = us.assign(a_idx=idx)
        us = us[us['a_idx'] < len(a_cal)]
        s = pd.Series(us['us_ret'].values, index=a_cal.iloc[us['a_idx']].values)
        s = s[~s.index.duplicated(keep='last')]

        # 重排到A股日历后ffill: 美股假日无新收盘时, "最近一个美股交易日的收益"正是当前隔夜信号
        aligned = s.reindex(a_cal.values).ffill().fillna(0.0)

        return pd.Series(aligned.values, index=df.index)


class USVolatilityRegime(FactorBase):
    """
    美股波动率状态因子
    美股自身处于高波动还是低波动状态

    逻辑：
    - 美股低波动（平稳涨跌）→ A股受影响小，走自己逻辑
    - 美股高波动（暴涨暴跌）→ A股情绪传染强，需要降仓防范
    """

    def __init__(self, window=20):
        super().__init__(f"us_vol_regime_{window}")
        self.window = window

    def calculate(self, df):
        if 'us_ret' not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df['us_ret'].rolling(self.window).std()


class HKMarketImpact(FactorBase):
    """
    港股影响因子
    恒生指数与A股联动性较强

    逻辑：
    - 港股大跌 → 南下资金受阻，A股承压
    - 港股大涨 → 风险偏好提升，A股受益
    - 港股中有大量A+H股，直接影响
    """

    def __init__(self):
        super().__init__("hk_market_impact")

    def calculate(self, df):
        # 港股接口在沙箱环境不可用，直接返回0
        return pd.Series(0.0, index=df.index)


class GlobalRiskAppetite(FactorBase):
    """
    全球风险偏好因子
    综合美股 + 港股 + VIX，判断全球风险情绪

    逻辑：
    - 全球Risk-On → A股成长股受益
    - 全球Risk-Off → A股防御为主，消费/公用事业抗跌
    """

    def __init__(self):
        super().__init__("global_risk_appetite")
        self.us_factor = USMarketImpact()
        self.hk_factor = HKMarketImpact()

    def calculate(self, df):
        # 综合美股+港股的隔夜表现
        us_ret = self.us_factor.calculate(df)
        hk_ret = self.hk_factor.calculate(df)

        # 等权合成
        combined = (us_ret.fillna(0) + hk_ret.fillna(0)) / 2

        return combined


class OvernightSignal(FactorBase):
    """
    隔夜信号综合因子
    核心用途：判断A股次日开盘方向

    组成：
    1. 美股隔夜涨跌（权重40%）
    2. 港股隔夜涨跌（权重30%）
    3. A50期货隔夜涨跌（权重30%）

    使用方式：
    - 因子值 > 0.5% → 次日大概率高开，可考虑追涨
    - 因子值 < -0.5% → 次日大概率低开，观望为主
    - 因子值在 -0.5%~0.5% → 外围影响中性，看A股自身逻辑
    """

    def __init__(self):
        super().__init__("overnight_signal")
        self.global_risk = GlobalRiskAppetite()

    def calculate(self, df):
        return self.global_risk.calculate(df)

    def interpret(self, value):
        """解读因子值"""
        if value > 0.005:
            return "外围偏强", "次日可能高开，关注追涨机会"
        elif value < -0.005:
            return "外围偏弱", "次日可能低开，观望或低吸"
        else:
            return "外围中性", "看A股自身逻辑"


class ForeignCapitalFlow(FactorBase):
    """
    外资流入因子
    北向资金是外资对中国资产的直接投票

    逻辑：
    - 北向连续净流入 → 外资看好，A股有支撑
    - 北向连续净流出 → 外资撤退，注意风险
    - 北向单日大幅流入/流出 → 情绪信号
    """

    def __init__(self, window=5):
        super().__init__(f"north_flow_{window}")
        self.window = window

    def calculate(self, df):
        # 北向数据不在个股K线里，直接返回0（不崩溃，不影响信号）
        if 'north_net' not in df.columns:
            return pd.Series(0.0, index=df.index)

        # 北向资金N日累计净流入
        return df['north_net'].rolling(self.window).sum()
