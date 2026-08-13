"""
市场状态判断 + 仓位管理
毛选核心:抓主要矛盾,不同时期不同打法

状态判断逻辑:
- BULL(牛市): MA短>MA长2%以上,波动率低,量价齐升
- BEAR(熊市): MA短<MA长2%以上,波动率高,量价齐跌
- SHOCK(震荡): 均线纠缠,趋势不明

仓位管理(敌进我退):
- BULL → 最大仓位100%,持仓上限5只
- SHOCK → 最大仓位60%,持仓上限3只
- BEAR → 最大仓位20%,持仓上限1只(或空仓)
"""
import pandas as pd
import numpy as np
from config import REGIME_CONFIG


class MarketRegime:
    """市场状态判断器 + 仓位管理器"""

    def __init__(self):
        self.cfg = REGIME_CONFIG
        self.ma_short = self.cfg['ma_short']
        self.ma_long = self.cfg['ma_long']
        self.vol_window = self.cfg['vol_window']

    def detect(self, index_df, policy_bias=None):
        """
        判断当前市场状态（调查研究 + 实事求是 + 政策维度）
        四维度：均线 + 波动率 + 市场结构（慢牛） + 政策偏置
        """
        if policy_bias is None:
            try:
                from config import POLICY_CONFIG
                policy_bias = int(POLICY_CONFIG.get('bias', 0))
            except Exception:
                policy_bias = 0
        close = index_df['close']
        volume = index_df['volume'] if 'volume' in index_df.columns else None

        # 均线
        ma_s = close.rolling(self.ma_short).mean().iloc[-1]
        ma_l = close.rolling(self.ma_long).mean().iloc[-1]

        # 波动率
        ret = close.pct_change()
        vol = ret.rolling(self.vol_window).std().iloc[-1]

        # 趋势强度: MA差值占比
        trend_strength = (ma_s - ma_l) / ma_l

        # 近期涨跌幅(20日)
        recent_return = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0

        # 成交量趋势
        vol_trend = 0
        if volume is not None and len(volume) >= 20:
            vol_ma5 = volume.rolling(5).mean().iloc[-1]
            vol_ma20 = volume.rolling(20).mean().iloc[-1]
            vol_trend = (vol_ma5 / vol_ma20 - 1) if vol_ma20 > 0 else 0

        # ========== 核心：慢牛结构判断 ==========
        # 慢牛 = 指数在高位区间运行，每次回调不破关键支撑（没创新低）
        # 熊市 = 指数持续下跌，屡创新低

        N_HIGH = 120  # 看120日高点（半年）
        high_120 = close.rolling(N_HIGH).max().iloc[-1]
        low_120 = close.rolling(N_HIGH).min().iloc[-1]
        recent_low = close.iloc[-20:].min()  # 最近20日低点

        # 从120日高点的回撤幅度（判断当前在高位还是低位）
        drawdown_from_high = (close.iloc[-1] - high_120) / high_120

        # 120日低点的位置（判断是否在慢牛通道内）
        # 如果当前价离120日高点<15%，且120日低点比再之前的低点高 → 慢牛
        HL_60 = close.rolling(60).min()  # 60日低点
        low_60_old = HL_60.iloc[-60] if len(HL_60) >= 60 else low_120
        low_60_recent = HL_60.iloc[-1]

        # 结构打分
        bull_score = 0
        bear_score = 0
        slow_bull_score = 0  # 慢牛专项分

        # 维度1: 均线
        if ma_s > ma_l * 1.02:
            bull_score += 2
        elif ma_s < ma_l * 0.98:
            bear_score += 2

        # 维度2: 波动率
        if vol < 0.012:
            bull_score += 1
        elif vol > 0.025:
            bear_score += 2
        elif vol > 0.018:
            bear_score += 1

        # 维度3: 近期涨跌
        if recent_return > 0.05:
            bull_score += 1
        elif recent_return < -0.04:
            bear_score += 1

        # 维度4: 量价配合
        if vol_trend > 0.1 and recent_return > 0:
            bull_score += 1
        elif vol_trend > 0.1 and recent_return < 0:
            bear_score += 1

        # ========== 慢牛专项判断（核心！）==========
        # 条件：指数在120日高点的-15%以内 + 60日低点没创新低
        # 关键：必须叠加"趋势确认"——均线不死叉 + 近20日不深跌
        # 教训(2026-07-14~08-03段3亏46%): 5/13见顶4242后一路阴跌,回撤10%在-15%阈值内被当"高位强势",
        # 实际均线已死叉、20日跌6%, 慢牛满分4分+政策2分硬判BULL → 追高接盘
        if drawdown_from_high > -0.15 and ma_s >= ma_l * 0.995 and recent_return > -0.03:
            slow_bull_score += 2  # 高位区间且趋势未破
            if low_60_recent >= low_60_old * 0.97:  # 底部抬升（允许3%误差）
                slow_bull_score += 2  # 逐底特征明显
        # 熊市趋势确认：均线死叉 + 近20日阴跌 → 下行趋势成立，直接计分
        elif ma_s < ma_l * 0.98 and recent_return < -0.04:
            bear_score += 2

        # 慢牛得分直接加权，重要性等同于其他维度
        bull_score += slow_bull_score

        # 政策维度（结合政策/新闻——实事求是，外部输入，越高越偏多）
        # 降权为±1：政策只能锦上添花/雪中送炭，不能翻盘技术面死叉（段3教训）
        if policy_bias > 0:
            bull_score += 1
        elif policy_bias < 0:
            bear_score += 1

        # 判定
        if bull_score >= 4 and bull_score > bear_score + 1:
            regime = "BULL"
        elif bear_score >= 3 and bear_score > bull_score + 1:
            regime = "BEAR"
        else:
            regime = "SHOCK"

        return {
            'regime': regime,
            'ma_short': round(ma_s, 2),
            'ma_long': round(ma_l, 2),
            'volatility': round(vol * 100, 2),
            'trend_strength': round(trend_strength * 100, 2),
            'recent_return': round(recent_return * 100, 2),
            'vol_trend': round(vol_trend * 100, 2),
            'bull_score': bull_score,
            'bear_score': bear_score,
            'slow_bull_score': slow_bull_score,
            'policy_bias': policy_bias,
            'policy_note': ('政策偏多' if policy_bias > 0 else '政策偏空' if policy_bias < 0 else '政策中性'),
            'drawdown_from_120high': round(drawdown_from_high * 100, 2),
            'high_120': round(high_120, 2),
            'description': self._describe(regime),
            'position_advice': self.get_position_advice(regime),
        }

    def _describe(self, regime):
        descs = {
            "BULL": "多头市场--主要矛盾是仓位和持有周期。动量为主,敢于追涨,集中兵力打歼灭战",
            "BEAR": "空头市场--主要矛盾是风控和回撤。防守为主,敌进我退,保存实力等待时机",
            "SHOCK": "震荡市场--主要矛盾是择时和节奏。反转为主,敌驻我扰,高抛低吸不贪心"
        }
        return descs.get(regime, "未知状态")

    def get_position_advice(self, regime):
        """仓位建议(敌进我退的落地)"""
        advice = {
            "BULL": {
                "max_position_pct": 1.0,    # 最大仓位100%
                "max_holdings": 5,           # 最多持仓5只
                "single_position_pct": 0.25, # 单只25%
                "strategy": "集中优势兵力,动量因子全开,趋势确认后加仓",
            },
            "SHOCK": {
                "max_position_pct": 0.6,    # 最大仓位60%
                "max_holdings": 3,           # 最多持仓3只
                "single_position_pct": 0.2,  # 单只20%
                "strategy": "轻仓试探,反转因子为主,高抛低吸,见好就收",
            },
            "BEAR": {
                "max_position_pct": 0.2,    # 最大仓位20%
                "max_holdings": 1,           # 最多持仓1只
                "single_position_pct": 0.15, # 单只15%
                "strategy": "保存实力,低仓位或空仓,只做超跌反弹,严格止损",
            }
        }
        return advice.get(regime, advice["SHOCK"])

    def get_factor_weights(self, regime):
        """
        不同市场状态下的因子权重(抓主要矛盾)
        这就是"具体问题具体分析"--不同时期用不同打法
        """
        weights = {
            # 牛市：打歼灭战，动量为王
            "BULL": {
                'momentum_20': 0.25,        # 动量：主攻方向
                'ma_align_5_20_60': 0.20,    # 均线排列：趋势确认
                'vol_price_div_20': 0.10,    # 量价背离：资金进场信号
                'turnover_avg_5': 0.08,      # 换手率：活跃度
                'reversal_5': 0.04,          # 反转：辅助
                'volatility_20': -0.08,      # 波动率：负权重，偏好稳定
                'us_market_impact': 0.10,    # 美股影响：牛市顺势加码
                'overnight_signal': 0.08,    # 隔夜信号：辅助
                'north_flow_5': 0.07,        # 北向资金：外资支撑
                # 说明：牛市的主要矛盾是“能不能拿住”，动量权重最大
                # 外围偏强时加码，不追涨停板，追趋势确认后的回踩 = 敌退我追
            },
            # 熊市：保存实力，防守为上
            "BEAR": {
                'momentum_20': -0.08,        # 动量：负权重，跌多了反而机会
                'reversal_5': 0.25,          # 反转：主攻方向（超跌反弹）
                'volatility_20': -0.20,      # 波动率：极度偏好低波动
                'amihud_20': -0.12,          # 流动性：偏好流动性好（随时能跑）
                'turnover_avg_5': 0.08,      # 换手率：适度活跃
                'ma_align_5_20_60': 0.07,    # 均线：轻微偏好多头
                'us_market_impact': 0.12,    # 美股影响：熊市外围影响更大
                'overnight_signal': 0.10,    # 隔夜信号：防低开
                'north_flow_5': -0.08,       # 北向资金：外资流出是风险信号
                # 说明：熊市的主要矛盾是“能不能活下来”，风控第一
                # 外围暴跌时避免抄底，只做超跌反弹，赚了就跑 = 敌进我退
            },
            # 震荡市：游击战，高抛低吸
            "SHOCK": {
                'reversal_5': 0.25,          # 反转：主攻方向
                'volatility_20': -0.15,      # 波动率：偏好低波动
                'turnover_spike_20': 0.15,    # 换手异动：情绪拐点
                'vol_price_div_20': 0.12,     # 量价背离：资金信号
                'momentum_20': 0.05,         # 动量：辅助
                'ma_align_5_20_60': 0.08,    # 均线：辅助
                'us_market_impact': 0.08,    # 美股影响：辅助
                'overnight_signal': 0.07,    # 隔夜信号：辅助
                'north_flow_5': 0.05,        # 北向资金：辅助
                # 说明：震荡市的主要矛盾是“节奏”，高抛低吸不贪心
                # 外围影响权重较低，主要看A股自身节奏
                # 轻仓试探，打一枪换一个地方 = 敌驻我扰
            }
        }
        return weights.get(regime, weights["SHOCK"])
