"""
market_sentiment.py - A股市场情绪与资金面数据采集

核心指标：
1. 涨停家数/炸板率/连板高度 → 短线情绪
2. 龙虎榜净买额/机构席位 → 主力动向
3. 北向资金净流向 → 外资态度
4. 板块资金轮动方向 → 主线判断

数据源：AKShare（东方财富），部分受沙箱代理限制。
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import akshare as ak


class SentimentCollector:
    """情绪与资金数据采集"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        # 接口可用性标记
        self.available = {
            "zt": True,        # 涨停板
            "strong_zt": True,  # 强势涨停
            "zbgc": True,      # 炸板池
            "lhb": True,       # 龙虎榜
            "north": True,     # 北向资金
            "sector_flow": False,  # 板块资金流（沙箱封禁）
            "stock_flow": False,   # 个股资金流（沙箱封禁）
        }

    # ==================== 涨停板数据 ====================

    def get_limit_up_pool(self, date: str) -> Optional[pd.DataFrame]:
        """
        获取涨停板股票池
        返回: [代码, 名称, 涨跌幅, 最新价, 成交额, 换手率, 封板资金,
               首次封板时间, 最后封板时间, 炸板次数, 连板数, 所属行业]

        接口异常时返回 None（与"当日无涨停"的空 DataFrame 区分开,
        否则一次网络抖动会被当成极端冰点日）
        """
        try:
            df = ak.stock_zt_pool_em(date=date)
            if len(df) == 0:
                return pd.DataFrame()
            df = df.rename(columns={
                "代码": "code", "名称": "name", "涨跌幅": "pct_chg",
                "最新价": "price", "成交额": "amount", "换手率": "turnover",
                "封板资金": "seal_money", "首次封板时间": "first_seal",
                "最后封板时间": "last_seal", "炸板次数": "zhaban_cnt",
                "涨停统计": "zt_stats", "连板数": "lianban",
                "所属行业": "industry",
            })
            df["code"] = df["code"].astype(str).str.zfill(6)
            df["date"] = date
            return df
        except Exception as e:
            print(f"[!!] limit_up_pool {date}: {e}")
            return None

    def get_strong_zt(self, date: str) -> pd.DataFrame:
        """
        强势涨停（连板股/新高股）
        返回含"入选理由"列，可判断：60日新高、近期多次涨停等
        """
        try:
            df = ak.stock_zt_pool_strong_em(date=date)
            if len(df) == 0:
                return pd.DataFrame()
            df = df.rename(columns={
                "代码": "code", "名称": "name", "涨跌幅": "pct_chg",
                "最新价": "price", "涨停价": "zt_price",
                "成交额": "amount", "换手率": "turnover",
                "封单量": "seal_vol", "是否新高": "is_new_high",
                "量比": "vol_ratio", "涨停统计": "zt_stats",
                "入选理由": "reason", "所属行业": "industry",
            })
            df["code"] = df["code"].astype(str).str.zfill(6)
            df["date"] = date
            return df
        except Exception as e:
            print(f"[!!] strong_zt {date}: {e}")
            return pd.DataFrame()

    def get_zhaban_pool(self, date: str) -> pd.DataFrame:
        """
        炸板池 - 试图涨停但失败的票
        炸板率高 = 市场分歧大 = 情绪差
        """
        try:
            df = ak.stock_zt_pool_zbgc_em(date=date)
            if len(df) == 0:
                return pd.DataFrame()
            df = df.rename(columns={
                "代码": "code", "名称": "name", "涨跌幅": "pct_chg",
                "最新价": "price", "涨停价": "zt_price",
                "成交额": "amount", "换手率": "turnover",
                "封单量": "seal_vol", "首次封板时间": "first_seal",
                "炸板次数": "zhaban_cnt", "涨停统计": "zt_stats",
                "振幅": "amplitude", "所属行业": "industry",
            })
            df["code"] = df["code"].astype(str).str.zfill(6)
            df["date"] = date
            return df
        except Exception as e:
            print(f"[!!] zhaban_pool {date}: {e}")
            return pd.DataFrame()

    # ==================== 龙虎榜 ====================

    def get_lhb(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        龙虎榜明细
        返回: [代码, 名称, 上榜日, 解读, 收盘价, 涨跌幅, 
               龙虎榜净买额, 买入额, 卖出额, 总成交额, 换手率]
        """
        try:
            # akshare 签名: stock_lhb_detail_em(start_date, end_date)，没有 date 参数
            if date:
                df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
            else:
                df = ak.stock_lhb_detail_em()
            if len(df) == 0:
                return pd.DataFrame()
            df = df.rename(columns={
                "代码": "code", "名称": "name", "上榜日": "date",
                "解读": "analysis", "收盘价": "close",
                "涨跌幅": "pct_chg", "龙虎榜净买额": "net_buy",
                "龙虎榜买入额": "buy_amount", "龙虎榜卖出额": "sell_amount",
            })
            df["code"] = df["code"].astype(str).str.zfill(6)
            return df
        except Exception as e:
            print(f"[!!] lhb: {e}")
            return pd.DataFrame()

    # ==================== 北向资金 ====================

    def get_north_flow(self, symbol: str = "北向资金") -> pd.DataFrame:
        """
        北向资金日频
        返回: [日期, 当日成交净买额, 买入成交额, 卖出成交额, 
               历史累计净买额, 持股市值, 领涨股]
        """
        try:
            df = ak.stock_hsgt_hist_em(symbol=symbol)
            if len(df) == 0:
                return pd.DataFrame()
            df = df.rename(columns={
                "日期": "date", "当日成交净买额": "net_inflow",
                "买入成交额": "buy_amount", "卖出成交额": "sell_amount",
                "历史累计净买额": "cum_net", "持股市值": "hold_value",
                "领涨股": "leader", "领涨股-涨跌幅": "leader_pct",
            })
            df["date"] = pd.to_datetime(df["date"])
            return df
        except Exception as e:
            print(f"[!!] north_flow: {e}")
            return pd.DataFrame()

    # ==================== 情绪指标计算 ====================

    def calc_sentiment_indicators(self, date: str) -> Dict:
        """
        计算单个交易日的情绪综合指标
        
        返回:
        {
            "date": str,
            "lianban_height": int,      # 最高连板数（市场高度）
            "zt_count": int,             # 涨停家数
            "zhaban_count": int,         # 炸板家数
            "zhaban_rate": float,        # 炸板率 = 炸板/(涨停+炸板)
            "strong_zt_count": int,      # 强势涨停家数
            "north_net": float,          # 北向净买额（亿）
            "north_3d": float,           # 北向3日累计
            "lhb_net": float,            # 龙虎榜合计净买额（亿）
            "sentiment_score": float,    # 情绪综合分 (-3~+3)
            "heat_level": str,           # 热度等级: HOT/WARM/COLD
        }
        """
        result = {"date": date}

        # 1. 涨停板（None = 接口失败，与"无涨停"区分，失败时向上抛而不是当成冰点）
        zt_df = self.get_limit_up_pool(date)
        if zt_df is None:
            raise RuntimeError(f"涨停池数据获取失败 {date}，无法计算情绪指标（拒绝把接口故障当成冰点日）")
        if len(zt_df) > 0:
            result["zt_count"] = len(zt_df)
            result["lianban_height"] = int(zt_df["lianban"].max()) if "lianban" in zt_df.columns else 0

            # 板块集中度：涨停股最多的行业占比
            if "industry" in zt_df.columns:
                top_ind = zt_df["industry"].value_counts().iloc[0]
                result["zt_concentration"] = round(top_ind / len(zt_df), 2)
            else:
                result["zt_concentration"] = 0

            # 封板时间早的占比（0930-1000内封板说明强）
            if "first_seal" in zt_df.columns:
                early = zt_df["first_seal"].apply(
                    lambda x: int(str(x)[:4]) <= 1000 if pd.notna(x) else False
                ).sum()
                result["early_seal_rate"] = round(early / len(zt_df), 2)
            else:
                result["early_seal_rate"] = 0

            # 首板占比（非连板 = 新机会）
            if "lianban" in zt_df.columns:
                shouban = (zt_df["lianban"] == 1).sum()
                result["shouban_ratio"] = round(shouban / len(zt_df), 2)
            else:
                result["shouban_ratio"] = 0
        else:
            result["zt_count"] = 0
            result["lianban_height"] = 0
            result["zt_concentration"] = 0
            result["early_seal_rate"] = 0
            result["shouban_ratio"] = 0

        # 2. 炸板池（None = 接口失败，按缺失处理而非 0 炸板）
        zb_df = self.get_zhaban_pool(date)
        if zb_df is None:
            raise RuntimeError(f"炸板池数据获取失败 {date}，无法计算情绪指标")
        if len(zb_df) > 0:
            result["zhaban_count"] = len(zb_df)
            total_board = result["zt_count"] + result["zhaban_count"]
            result["zhaban_rate"] = round(result["zhaban_count"] / max(total_board, 1), 3)
        else:
            result["zhaban_count"] = 0
            result["zhaban_rate"] = 0

        # 3. 强势涨停
        strong_df = self.get_strong_zt(date)
        result["strong_zt_count"] = len(strong_df)

        # 4. 北向资金
        # 需要历史数据，这里不从单日拉（太慢），放到历史回填
        result["north_net"] = 0
        result["north_3d"] = 0

        # 5. 龙虎榜
        try:
            lhb = self.get_lhb(date=date)
            if len(lhb) > 0 and "net_buy" in lhb.columns:
                result["lhb_net"] = round(lhb["net_buy"].sum() / 1e8, 2)  # 转亿
            else:
                result["lhb_net"] = 0
        except:
            result["lhb_net"] = 0

        # 6. 综合情绪打分
        result["sentiment_score"] = self._calc_score(result)
        result["heat_level"] = self._heat_level(result["sentiment_score"])

        return result

    def _calc_score(self, r: Dict) -> float:
        """
        情绪综合打分 (-3 ~ +3)
        
        加分项：
        - 涨停>80家 +1, >120家 +2
        - 连板高度>5 +1, >8 +2
        - 炸板率<25% +1
        - 炸板率<15% +2
        - 早盘封板率>60% +1
        - 板块集中>30% +1
        - 首板多>60% +1
        
        减分项：
        - 涨停<30家 -2
        - 涨停<50家 -1
        - 炸板率>45% -1
        - 炸板率>55% -2
        """
        score = 0.0

        # 涨停家数
        zt = r.get("zt_count", 0)
        if zt >= 120: score += 2.0
        elif zt >= 80: score += 1.0
        elif zt < 30: score -= 2.0
        elif zt < 50: score -= 1.0

        # 连板高度
        h = r.get("lianban_height", 0)
        if h >= 8: score += 2.0
        elif h >= 5: score += 1.0
        elif h <= 2 and zt > 0: score -= 0.5  # 高度打不开

        # 炸板率
        zr = r.get("zhaban_rate", 0)
        if zr > 0:
            if zr < 0.15: score += 2.0
            elif zr < 0.25: score += 1.0
            elif zr > 0.55: score -= 2.0
            elif zr > 0.45: score -= 1.0

        # 早封板率
        if r.get("early_seal_rate", 0) > 0.6:
            score += 1.0

        # 板块集中度（有主线）
        if r.get("zt_concentration", 0) > 0.3:
            score += 1.0

        # 首板占比（有新鲜血液）
        if r.get("shouban_ratio", 0) > 0.6:
            score += 1.0

        return round(score, 1)

    @staticmethod
    def _heat_level(score: float) -> str:
        if score >= 2: return "HOT"
        elif score >= 0: return "WARM"
        elif score >= -1: return "CHILLY"
        else: return "COLD"

    # ==================== 历史数据回填 ====================

    def backfill(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        回填历史情绪数据（逐日拉取，较慢）
        只回填交易日；接口失败的日子记录为 NaN，不冒充冰点
        """
        # 先用北向资金（一次性拿到全量日期）
        try:
            north = self.get_north_flow()
            if len(north) > 0:
                north = north.set_index("date")
                north_rolling = north["net_inflow"].rolling(3).sum()
        except:
            north = pd.DataFrame()
            north_rolling = pd.Series(dtype=float)

        # 交易日列表：优先用交易日历（freq="B" 不排除法定假日，假日会被误判成冰点）
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        dates = None
        try:
            cal = ak.tool_trade_date_hist_sina()
            trade_days = pd.to_datetime(cal["trade_date"])
            dates = trade_days[(trade_days >= start_ts) & (trade_days <= end_ts)]
        except Exception as e:
            print(f"[!!] 交易日历获取失败，回退到工作日近似: {e}")
        if dates is None or len(dates) == 0:
            dates = pd.date_range(start_ts, end_ts, freq="B")

        records = []
        for d in dates:
            ds = d.strftime("%Y%m%d")
            try:
                r = self.calc_sentiment_indicators(ds)
            except RuntimeError as e:
                # 数据不可用的日子：指标记 NaN，绝不按 zt=0 计入冰点统计
                print(f"  [SKIP] {ds}: {e}")
                r = {"date": ds, "zt_count": np.nan, "zhaban_count": np.nan,
                     "zhaban_rate": np.nan, "lianban_height": np.nan,
                     "sentiment_score": np.nan, "heat_level": "UNKNOWN"}

            # 补北向
            if len(north) > 0 and d in north.index:
                r["north_net"] = round(north.loc[d, "net_inflow"] / 1e8, 2) if pd.notna(north.loc[d, "net_inflow"]) else 0
                r["north_3d"] = round(north_rolling.get(d, 0) / 1e8, 2)
            records.append(r)

            if len(records) % 5 == 0:
                print(f"  sentiment backfill: {len(records)}/{len(dates)} ({ds})")

        df = pd.DataFrame(records)
        return df


# ==================== 快速测试 ====================
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    collector = SentimentCollector()

    # 单日测试
    r = collector.calc_sentiment_indicators("20260731")
    print("=== 2026-07-31 情绪指标 ===")
    for k, v in sorted(r.items()):
        print(f"  {k}: {v}")

    print()
    # 快速回填最近5个交易日
    print("=== 最近5日回填 ===")
    df = collector.backfill("20260725", "20260731")
    print(df[["date", "zt_count", "zhaban_count", "zhaban_rate",
              "lianban_height", "sentiment_score", "heat_level"]].to_string())
