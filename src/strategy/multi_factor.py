"""
多因子选股策略
核心逻辑：
1. 调查研究：判断市场状态
2. 抓主要矛盾：根据状态选因子权重
3. 集中优势兵力：信号强的优先配置资金
4. 实事求是：因子打分用数据说话
"""
import pandas as pd
import numpy as np
from src.factors.base import FactorEngine
from src.factors.price_volume import (
    Momentum, Reversal, Volatility, Turnover,
    VolumePriceDivergence, MAAlign, AmihudIlliquidity
)
from src.factors.sentiment import TurnoverSpike, PriceGap, LimitUpCount
from src.factors.fundamental import (
    PEFactor, PBFactor, ProsperityFactor, IndustryRotation, MarketCap
)
from src.factors.overseas import (
    USMarketImpact, GlobalRiskAppetite, OvernightSignal, ForeignCapitalFlow
)
from src.utils.market_regime import MarketRegime
from src.utils.position_manager import PositionManager


class MultiFactorStrategy:
    """多因子选股策略 - 毛选思想驱动"""

    def __init__(self):
        self.engine = FactorEngine()
        self.regime = MarketRegime()
        self.pos_manager = PositionManager()
        self._factor_warned = set()  # 因子异常只告警一次，避免刷屏

        # 注册因子（全部注册，根据市场状态动态调权重）
        self._register_factors()

    def _register_factors(self):
        """注册所有因子"""
        # 量价因子
        price_vol_factors = [
            Momentum(20),          # 动量
            Reversal(5),            # 反转
            Volatility(20),         # 波动率
            Turnover(5),            # 换手率
            MAAlign(5, 20, 60),     # 均线排列
            AmihudIlliquidity(20),  # 非流动性
            VolumePriceDivergence(20),  # 量价背离（代替量比）
        ]
        # 情绪因子
        sentiment_factors = [
            TurnoverSpike(20),      # 换手异动
            PriceGap(),             # 跳空缺口
            LimitUpCount(),         # 涨停连板
        ]
        # 基本面因子（景气度方向）
        fundamental_factors = [
            PEFactor(),             # 市盈率
            PBFactor(),             # 市净率
            ProsperityFactor(),     # 景气度（核心）
            IndustryRotation(20),   # 行业轮动（找主线）
            MarketCap(),            # 市值
        ]
        # 外围市场因子（美股影响）
        overseas_factors = [
            USMarketImpact(),       # 美股隔夜影响
            GlobalRiskAppetite(),   # 全球风险偏好
            OvernightSignal(),      # 隔夜信号综合
            ForeignCapitalFlow(5),  # 北向资金
        ]

        all_factors = price_vol_factors + sentiment_factors + fundamental_factors + overseas_factors
        for f in all_factors:
            self.engine.register(f)

        print(f"已注册 {len(all_factors)} 个因子")

    def generate_signals(self, data_dict, index_df, pool=None):
        """
        生成交易信号
        完整流程：调查研究 → 抓主要矛盾 → 因子打分 → 选股

        参数:
            data_dict: {code: DataFrame} 日线数据
            index_df: 指数数据
            pool: 股票池（可选，用于过滤）

        返回: DataFrame[date, code, signal, score, regime]
        """
        # === 1. 调查研究：判断市场状态 ===
        market_state = self.regime.detect(index_df)
        regime_name = market_state['regime']
        print(f"\n=== 市场状态 ===")
        print(f"  状态: {regime_name}")
        print(f"  {market_state['description']}")
        print(f"  MA{self.regime.ma_short}: {market_state['ma_short']} | MA{self.regime.ma_long}: {market_state['ma_long']}")
        print(f"  波动率: {market_state['volatility']}% | 趋势强度: {market_state['trend_strength']}%")

        # === 2. 抓主要矛盾：获取因子权重 ===
        weights = self.regime.get_factor_weights(regime_name)
        pos_advice = market_state['position_advice']
        print(f"\n  仓位建议: 最多{pos_advice['max_holdings']}只, 最大仓位{pos_advice['max_position_pct']*100:.0f}%")
        print(f"  策略: {pos_advice['strategy']}")

        # === 3. 因子计算 ===
        factor_df = self.engine.calculate_batch(data_dict)
        if len(factor_df) == 0:
            print("  无可用因子数据")
            return pd.DataFrame()

        # 股票池过滤
        if pool is not None:
            pool_codes = pool['code'].astype(str).tolist()
            factor_df = factor_df[factor_df['code'].isin(pool_codes)]

        # === 4. 实事求是：因子标准化 + 加权打分 ===
        factor_cols = [c for c in factor_df.columns if c != 'code']

        # z-score标准化
        for col in factor_cols:
            vals = factor_df[col]
            mean = vals.mean()
            std = vals.std()
            if std > 0:
                factor_df[col] = (vals - mean) / std
            else:
                factor_df[col] = 0

        # 加权打分（只用在当前市场状态下有权重的因子）
        score = pd.Series(0.0, index=factor_df.index)
        used_factors = []
        for factor_name, weight in weights.items():
            if factor_name in factor_df.columns:
                score += factor_df[factor_name].fillna(0) * weight
                used_factors.append(f"{factor_name}({weight:+.2f})")

        factor_df['score'] = score
        print(f"\n  使用因子: {', '.join(used_factors)}")

        # === 5. 生成信号 ===
        # 分位数法：前20%买入，后20%卖出
        q80 = factor_df['score'].quantile(0.80)
        q20 = factor_df['score'].quantile(0.20)

        factor_df['signal'] = 0
        factor_df.loc[factor_df['score'] >= q80, 'signal'] = 1   # 买入
        factor_df.loc[factor_df['score'] <= q20, 'signal'] = -1  # 卖出

        # 信号强度 = 分数在分位数之外的程度
        factor_df.loc[factor_df['signal'] == 1, 'signal_strength'] = (
            (factor_df['score'] - q80) / (factor_df['score'].max() - q80 + 1e-8)
        )
        factor_df.loc[factor_df['signal'] == -1, 'signal_strength'] = (
            (q20 - factor_df['score']) / (q20 - factor_df['score'].min() + 1e-8)
        )
        factor_df['signal_strength'] = factor_df['signal_strength'].fillna(0)

        # 添加日期和状态
        today = pd.Timestamp.now().strftime('%Y-%m-%d')
        factor_df['date'] = today
        factor_df['regime'] = regime_name

        # 按分数排序
        result = factor_df[['date', 'code', 'signal', 'signal_strength', 'score', 'regime']].sort_values(
            'score', ascending=False
        )

        # 打印结果
        buy_list = result[result['signal'] > 0].head(20)
        print(f"\n=== 买入信号前20 ===")
        if len(buy_list) > 0 and pool is not None:
            buy_display = buy_list.merge(
                pool[['code', 'name']], on='code', how='left'
            )
            print(buy_display[['code', 'name', 'score', 'signal_strength']].to_string(index=False))
        else:
            print(buy_list[['code', 'score', 'signal_strength']].to_string(index=False))

        return result

    def precompute_factor_panels(self, data_dict, factor_names=None):
        """
        预计算因子面板(向量化提速, 结果与逐日切片计算严格等价)

        前提: 所有因子后视纯(第t行值只由≤t数据决定, 见 ARCHITECTURE.md 契约),
        因此"全历史算一次再按行取" ≡ "每个日期切片算一遍取末行"。

        返回: {code: {'dates': np.ndarray(有序), 'factors': {fname: np.ndarray}}}
        """
        if factor_names is None:
            # 各状态权重表并集(只算会被用到的因子)
            factor_names = set()
            for regime in ('BULL', 'BEAR', 'SHOCK'):
                factor_names |= set(self.regime.get_factor_weights(regime).keys())
            factor_names &= set(self.engine.factors.keys())

        panels = {}
        for code, df in data_dict.items():
            if df is None or len(df) == 0:
                continue
            if not df['date'].is_monotonic_increasing:
                df = df.sort_values('date').reset_index(drop=True)
            dates = pd.to_datetime(df['date']).values
            factors = {}
            for fname in factor_names:
                f = self.engine.factors[fname]
                try:
                    s = f.calculate(df)
                except Exception as e:
                    if fname not in self._factor_warned:
                        self._factor_warned.add(fname)
                        print(f"  [WARN] 因子 {fname} 面板计算异常(仅报一次): {e}")
                    continue
                if not isinstance(s, pd.Series) or len(s) != len(df):
                    continue
                factors[fname] = np.asarray(s, dtype=float)
            panels[code] = {'dates': dates, 'factors': factors}
        return panels

    def cross_section_records(self, panels, all_dates):
        """
        逐日横截面: 对每个交易日T, 取每只股票 date<T 的最后一行因子值
        (信号日T用T-1收盘数据, T开盘成交 —— 时序契约)

        返回: {date: [ {code, fname: value, ...}, ... ]} 只含有足够历史(≥60行)的股票
        """
        # searchsorted 需要严格 datetime64 数组(list of Timestamp 会变成 object dtype 报错);
        # 字典键保留调用方传入的原始日期对象, 保证 get(date) 命中
        all_dates_arr = np.asarray(pd.to_datetime(list(all_dates)), dtype='datetime64[ns]')
        lookup = {}
        for code, panel in panels.items():
            dates_c = panel['dates']
            # 每个T对应 date<T 的行号: searchsorted(left)-1
            pos = np.searchsorted(dates_c, all_dates_arr, side='left')
            row = pos - 1
            valid = (pos >= 60)  # 等价于原 mask.sum() >= 60 的最少历史要求
            lookup[code] = {'row': np.where(valid, row, -1), 'factors': panel['factors']}

        out = {}
        for i, T in enumerate(all_dates):
            records = []
            for code, lu in lookup.items():
                r = lu['row'][i]
                if r < 0:
                    continue
                rec = {'code': code}
                for fname, arr in lu['factors'].items():
                    rec[fname] = arr[r]
                records.append(rec)
            out[T] = records
        return out

    def backtest_with_regime(self, data_dict, index_df, pool=None, start_date=None, end_date=None):
        """
        带市场状态判断的回测（毛选版）
        每个交易日：调查研究(判状态) → 横截面z-score(实事求是) → 抓主要矛盾(加权) → 集中优势兵力(分位数选股)

        性能: 因子面板一次性预计算(precompute_factor_panels), 逐日只做行查找,
        与旧的逐(日期×股票)切片重算路径严格等价(见 tests/test_factor_panel.py)。

        关键修复（历史）：
        1) 因子值必须做横截面 z-score 标准化，否则 PE/市值(万亿) 与 动量/波动率(0.0x) 量纲混战
        2) 信号生成用分位数筛选（前20%买入/后20%卖出），而非 score>0 全买
        """
        from src.backtest.engine import BacktestEngine

        all_dates = sorted(pd.to_datetime(index_df['date'].unique()))
        valid_codes = list(data_dict.keys())

        # 预计算 + 逐日横截面(取代逐日×逐股切片重算)
        panels = self.precompute_factor_panels(data_dict)
        records_by_date = self.cross_section_records(panels, all_dates)

        all_signals = []
        for i, date in enumerate(all_dates):
            if start_date and pd.Timestamp(date) < pd.Timestamp(start_date):
                continue
            if end_date and pd.Timestamp(date) > pd.Timestamp(end_date):
                continue

            # 决策基准 = T-1 收盘（信号在 T 开盘成交，绝不能用 T 收盘算因子）
            index_up_to = index_df[index_df['date'] < date]
            if len(index_up_to) < 60:
                continue

            market_state = self.regime.detect(index_up_to)
            weights = self.regime.get_factor_weights(market_state['regime'])

            # 1) 横截面因子值(预计算面板行查找)
            records = records_by_date.get(date, [])
            if len(records) < 30:
                continue

            fac_df = pd.DataFrame(records)

            # 2) 横截面 z-score 标准化（消除量纲，实事求是）
            for fname in list(weights.keys()):
                if fname not in fac_df.columns:
                    continue
                s = fac_df[fname]
                m = s.mean()
                sd = s.std()
                if sd and not np.isnan(sd) and sd > 0:
                    fac_df[fname + '_z'] = (s - m) / sd
                else:
                    fac_df[fname + '_z'] = 0.0

            # 3) 加权综合得分（只加有权重的因子，缺失按0）
            fac_df['score'] = 0.0
            for fname, w in weights.items():
                zc = fname + '_z'
                if zc in fac_df.columns:
                    fac_df['score'] += fac_df[zc].fillna(0) * w

            # 4) 集中优势兵力：分位数筛选（前20%买入，后20%卖出）
            buy_q = fac_df['score'].quantile(0.80)
            sell_q = fac_df['score'].quantile(0.20)
            fac_df['signal'] = 0
            fac_df.loc[fac_df['score'] >= buy_q, 'signal'] = 1
            fac_df.loc[fac_df['score'] <= sell_q, 'signal'] = -1

            for _, row in fac_df.iterrows():
                all_signals.append({
                    'date': date,
                    'code': row['code'],
                    'signal': int(row['signal']),
                    'score': float(row['score']),
                })

            if (i + 1) % 20 == 0:
                print(f"  回测进度: {i+1}/{len(all_dates)} | 状态:{market_state['regime']} | 候选:{len(fac_df)} | 买:{int((fac_df['signal']==1).sum())} 卖:{int((fac_df['signal']==-1).sum())}")

        if not all_signals:
            print("[!] 无有效信号")
            return None

        signals_df = pd.DataFrame(all_signals)
        engine = BacktestEngine()
        result = engine.run(signals_df, data_dict, index_df)
        return result
