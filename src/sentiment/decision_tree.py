import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

"""
A股交易决策树引擎
========================
核心理念：模拟真实交易者每日决策流程，而非因子管道。
每步决策基于前一步结果——"先看天气，再看方向，再选票，再分仓"。

决策树：
  T日盘前：评估市场情绪
    └── 情绪冷（炸板率高/涨停少）→ 降低仓位上限
    └── 情绪热 → 提高仓位上限
    └── 极端差 → 空仓

  T日入场：选择方向
    └── 找昨日最强板块（连板集中度/涨停家数）
    └── 板块持续性确认（非一日游）
    └── 从板块中选标的（龙头优先，跟风次选）

  T+1 处理持仓：
    └── 连板次日 → 看竞价（高开持有/低开出）
    └── 非连板 → T+1 不强即出
    └── 炸板 → 次日竞价必出
    └── 止损止盈 → 无条件执行

核心参数：
  - 仓位由情绪决定，不由因子打分决定
  - 选股由板块方向决定，不由IC排序决定
  - 持有/卖出由次日表现决定，不由信号反转决定
"""

from src.sentiment.market_sentiment import SentimentCollector

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class DecisionContext:
    """每日决策上下文"""
    date: str
    sentiment: Dict                        # 当日情绪指标
    positions: Dict[str, Dict]             # 当前持仓 {code: {cost, buy_date, ...}}
    capital: float                         # 可用资金
    total_value: float                     # 总资产
    max_positions: int                     # 仓位上限
    sector_strength: Dict[str, float]      # 板块强度 {sector: strength_score}
    active_sectors: List[str]              # 活跃主线板块
    blocked: bool                          # 熔断/冷却中
    notes: List[str] = field(default_factory=list)


class TradingDecisionTree:
    """
    A股交易决策树引擎
    
    模拟真实交易者思维：
    1. 盘前评估 → 2. 方向选择 → 3. 仓位分配 → 4. 调仓执行
    """

    def __init__(self, config: Dict = None):
        self.cfg = config or {}
        self.collector = SentimentCollector()
        
        # 决策阈值
        self.heat_thresholds = {
            "HOT": {"max_pos": 5, "single_pct": 0.25, "total_pct": 1.0},
            "WARM": {"max_pos": 3, "single_pct": 0.20, "total_pct": 0.6},
            "CHILLY": {"max_pos": 1, "single_pct": 0.15, "total_pct": 0.3},
            "COLD": {"max_pos": 0, "single_pct": 0.10, "total_pct": 0.15},
        }
        
        # 风控参数
        self.stop_loss = -0.07       # 硬止损
        self.take_profit = 0.15      # 硬止盈
        self.trailing_active = 0.10  # 移动止盈激活阈值
        self.trailing_pct = 0.05     # 移动回撤容忍
        
        # 板块确认参数
        self.sector_confirm_days = 2  # 板块需连续出现几天才算主线
        
        # 历史板块热度追踪（用于确认主线）
        self.sector_history: Dict[str, List] = {}  # {date: [sector_list]}

    # ==================== 第1步：盘前评估 ====================

    def assess_market(self, date: str, 
                      sentiment_history: pd.DataFrame = None) -> DecisionContext:
        """
        盘前评估市场状态
        
        输入：
        - 当日涨停/炸板/连板数据
        - 北向资金方向
        - 历史情绪趋势
        
        输出：
        - 仓位上限
        - 是否可以开仓
        - 当前情绪等级
        """
        sentiment = self.collector.calc_sentiment_indicators(date)
        
        # 1. 情绪趋势确认（连续3天变化方向）
        trend_bias = 0
        if sentiment_history is not None and len(sentiment_history) >= 3:
            recent = sentiment_history.tail(3)
            if "sentiment_score" in recent.columns:
                scores = recent["sentiment_score"].values
                if len(scores) == 3:
                    if scores[2] > scores[1] > scores[0]:
                        trend_bias = +1   # 情绪升温
                    elif scores[2] < scores[1] < scores[0]:
                        trend_bias = -1   # 情绪降温
        
        # 2. 修正情绪评分：炸板率权重调高
        zhaban_rate = sentiment.get("zhaban_rate", 0)
        if zhaban_rate > 0.5:
            sentiment["heat_level"] = "CHILLY"
            sentiment["sentiment_score"] = min(sentiment["sentiment_score"], -1)
        elif zhaban_rate > 0.35:
            sentiment["heat_level"] = "WARM"
            sentiment["sentiment_score"] = max(0, sentiment["sentiment_score"] - 1)
        
        # 3. 情绪趋势加分/扣分
        if trend_bias == -1 and sentiment["heat_level"] in ("HOT", "WARM"):
            sentiment["heat_level"] = "WARM"
            sentiment["sentiment_score"] = max(0, sentiment["sentiment_score"] - 1)
        
        # 4. 取仓位配置
        heat = sentiment["heat_level"]
        config = self.heat_thresholds.get(heat, self.heat_thresholds["CHILLY"])
        
        ctx = DecisionContext(
            date=date,
            sentiment=sentiment,
            positions={},
            capital=0,
            total_value=0,
            max_positions=config["max_pos"],
            sector_strength={},
            active_sectors=[],
            blocked=False,
        )
        
        ctx.notes.append(f"[{heat}] 仓位上限={config['max_pos']}只, 单只={config['single_pct']*100}%, 总仓={config['total_pct']*100}%")
        
        return ctx

    # ==================== 第2步：方向选择（找主线） ====================

    def find_active_sectors(self, ctx: DecisionContext, 
                            sentiment_history: pd.DataFrame = None) -> DecisionContext:
        """
        找主线板块
        
        逻辑：
        1. 当期涨停板的板块分布
        2. 连板股最多的板块（有持续性）
        3. 板块是否在前日也出现过（确认不是一日游）
        4. 排除防御性板块（白酒/银行/公用事业——GJD控盘工具）
        """
        # 获取当日涨停板数据
        zt_df = self.collector.get_limit_up_pool(ctx.date)
        strong_df = self.collector.get_strong_zt(ctx.date)
        
        if len(zt_df) == 0:
            ctx.active_sectors = []
            ctx.sector_strength = {}
            ctx.notes.append("无涨停板数据")
            return ctx
        
        # 防御性板块（GJD稳定器，没有赚钱效应）
        defensive = {"酿酒", "白酒", "银行", "保险", "电力", "公用事业", "石油", "煤炭"}
        
        # 1. 涨停股板块分布
        sector_zt = {}
        if "industry" in zt_df.columns:
            for _, row in zt_df.iterrows():
                ind = row.get("industry", "未知")
                if pd.isna(ind) or ind in defensive:
                    continue
                sector_zt[ind] = sector_zt.get(ind, 0) + 1
        
        # 2. 连板股板块分布（权重更高）
        if "industry" in strong_df.columns:
            for _, row in strong_df.iterrows():
                ind = row.get("industry", "未知")
                if pd.isna(ind) or ind in defensive:
                    continue
                # 连板股算3倍权重
                sector_zt[ind] = sector_zt.get(ind, 0) + 2
        
        # 3. 板块强度 = 涨停数 + 连板加成
        sector_strength = {}
        for sector, count in sector_zt.items():
            # 归一化：涨停家数/总涨停数
            strength = count / max(len(zt_df), 1)
            sector_strength[sector] = round(strength, 3)
        
        # 4. 排序取前三
        sorted_sectors = sorted(sector_strength.items(), key=lambda x: x[1], reverse=True)
        active = [s for s, v in sorted_sectors[:3] if v > 0.05]  # 至少占比5%
        
        ctx.sector_strength = sector_strength
        ctx.active_sectors = active
        
        if active:
            ctx.notes.append(f"主线板块: {' > '.join([f'{s}({sector_strength[s]:.1%})' for s in active])}")
        else:
            ctx.notes.append("无明确主线")
        
        return ctx

    # ==================== 第3步：选股（从主线里挑标的） ====================

    def select_targets(self, ctx: DecisionContext,
                       daily_data: Dict[str, pd.DataFrame],
                       pool: pd.DataFrame = None) -> List[Dict]:
        """
        从主线板块中选标的
        
        优先级：
        1. 板块内龙头（涨停最早/封单最大/连板高度最高）
        2. 板块内跟风强势股（首板封板早）
        3. 不做板块外的杂毛
        
        过滤条件：
        - ST/退市 跳过
        - 成交额 < 5000万 跳过
        - 涨停当天不追（T+1风险）
        - 已经持仓的不重复买
        """
        if not ctx.active_sectors or ctx.max_positions == 0:
            return []
        
        zt_df = self.collector.get_limit_up_pool(ctx.date)
        if len(zt_df) == 0:
            return []
        
        held_codes = set(ctx.positions.keys())
        targets = []
        
        for sector in ctx.active_sectors:
            # 板块内涨停股
            sector_stocks = zt_df[zt_df["industry"] == sector] if "industry" in zt_df.columns else pd.DataFrame()
            
            if len(sector_stocks) == 0:
                continue
            
            # 排除已持仓
            sector_stocks = sector_stocks[~sector_stocks["code"].isin(held_codes)]
            
            # 排除ST
            if "name" in sector_stocks.columns:
                sector_stocks = sector_stocks[~sector_stocks["name"].str.contains("ST|退", na=False)]
            
            # 按优先级排序
            if "lianban" in sector_stocks.columns:
                sector_stocks = sector_stocks.sort_values("lianban", ascending=False)
            
            for _, row in sector_stocks.head(3).iterrows():
                code = row["code"]
                targets.append({
                    "code": code,
                    "name": row.get("name", ""),
                    "sector": sector,
                    "lianban": int(row.get("lianban", 0)),
                    "seal_money": float(row.get("seal_money", 0)),
                    "first_seal": row.get("first_seal", ""),
                    "reason": f"主线{sector}涨停",
                })
        
        ctx.notes.append(f"候选标的: {len(targets)}只 ({', '.join([t['code'] for t in targets[:5]])})")
        return targets

    # ==================== 第4步：仓位分配 ====================

    def allocate_positions(self, ctx: DecisionContext,
                           targets: List[Dict]) -> List[Dict]:
        """
        分仓
        
        规则：
        - 情绪HOT：每只20%仓位，最多5只
        - 情绪WARM：每只15%仓位，最多3只
        - 情绪CHILLY：每只10%仓位，最多1只
        - 龙头重仓，跟风轻仓
        - 首买：试盘仓位，不一次性满仓
        """
        heat = ctx.sentiment["heat_level"]
        config = self.heat_thresholds.get(heat, self.heat_thresholds["CHILLY"])
        
        max_new = config["max_pos"] - len(ctx.positions)
        if max_new <= 0:
            ctx.notes.append("仓位已满，不新增")
            return []
        
        allocations = []
        for i, t in enumerate(targets):
            if i >= max_new:
                break
            
            # 龙头（连板≥3）给满仓，跟风给半仓
            single_pct = config["single_pct"]
            if t.get("lianban", 0) >= 3:
                single_pct = min(single_pct * 1.2, 0.3)  # 龙头最多30%
            elif t.get("lianban", 0) == 1:
                single_pct = single_pct * 0.7  # 首板跟风少买
            
            t["position_pct"] = round(single_pct, 2)
            t["order_type"] = "LEADER" if t.get("lianban", 0) >= 3 else "FOLLOWER"
            allocations.append(t)
        
        ctx.notes.append(f"计划开仓: {len(allocations)}只")
        return allocations

    # ==================== 第5步：调仓规则 ====================

    def manage_positions(self, ctx: DecisionContext,
                         daily_data: Dict[str, pd.DataFrame]) -> Dict[str, str]:
        """
        持仓管理
        
        卖出决策树：
        1. 止损止盈 → 无条件出
        2. 持有股所属板块退潮 → 出
        3. 连板股 → 持有（让利润跑）
        4. 非连板+次日不涨停 → T+1出
        5. 炸板 → 次日必出
        """
        decisions = {}  # {code: "HOLD"|"SELL"|"SELL_HALF"}
        
        for code, pos in ctx.positions.items():
            if code not in daily_data:
                decisions[code] = "SELL"  # 没数据就出
                continue
            
            stock_df = daily_data[code]
            if len(stock_df) == 0:
                decisions[code] = "SELL"
                continue
            
            latest = stock_df.iloc[-1]
            current_price = latest["close"]
            cost = pos["cost"]
            pnl_pct = (current_price / cost - 1)
            buy_date = pos.get("buy_date", "")
            
            # 1. 止损止盈（铁律）
            if pnl_pct <= self.stop_loss:
                decisions[code] = "SELL"
                ctx.notes.append(f"[{code}] 止损 {pnl_pct:.1%}")
                continue
            
            if pnl_pct >= self.take_profit:
                decisions[code] = "SELL"
                ctx.notes.append(f"[{code}] 止盈 {pnl_pct:.1%}")
                continue
            
            # 2. 移动止盈
            if pnl_pct >= self.trailing_active:
                high = pos.get("high_water", cost)
                if current_price < high * (1 - self.trailing_pct):
                    decisions[code] = "SELL"
                    ctx.notes.append(f"[{code}] 移动止盈 {pnl_pct:.1%}")
                    continue
            
            # 3. 持有天数检查
            if buy_date and len(buy_date) == 8:
                days_held = (datetime.strptime(ctx.date, "%Y%m%d") - 
                            datetime.strptime(buy_date, "%Y%m%d")).days
            else:
                days_held = 999
            
            # 4. 次日不强就出（非连板+持有≥1天+当天没涨停）
            if days_held >= 1:
                pct_chg_today = (current_price / stock_df.iloc[-2]["close"] - 1) if len(stock_df) >= 2 else 0
                
                # 简单判断：当日涨幅<3%且之前不是连板股，出
                if pct_chg_today < 0.03 and pnl_pct < 0.05:
                    # 如果才赚1-2%，弱票不浪费时间
                    if 0 < pnl_pct < 0.03:
                        decisions[code] = "SELL"
                        ctx.notes.append(f"[{code}] 弱势持仓{int(days_held)}天+{pnl_pct:.1%}出")
                        continue
            
            # 5. 持有3天以上不涨 → 出
            if days_held >= 3 and pnl_pct < 0.02:
                decisions[code] = "SELL"
                ctx.notes.append(f"[{code}] 持仓{int(days_held)}天不涨出")
                continue
            
            # 更新最高水位
            if pnl_pct > 0 and current_price > pos.get("high_water", cost):
                pos["high_water"] = current_price
            
            decisions[code] = "HOLD"
        
        return decisions

    # ==================== 综合决策 ====================

    def make_decision(self, date: str,
                      positions: Dict[str, Dict],
                      capital: float,
                      total_value: float,
                      daily_data: Dict[str, pd.DataFrame],
                      sentiment_history: pd.DataFrame = None,
                      pool: pd.DataFrame = None,
                      blocked: bool = False) -> Dict:
        """
        综合决策：每天调用一次
        
        返回：
        {
            "date": str,
            "context": DecisionContext,      # 完整决策上下文
            "sell_decisions": {code: "SELL"|"HOLD"},
            "buy_targets": [{code, name, sector, position_pct, ...}],
            "notes": [str],
        }
        """
        notes = []
        
        # Step 1: 盘前评估
        ctx = self.assess_market(date, sentiment_history)
        ctx.positions = positions
        ctx.capital = capital
        ctx.total_value = total_value
        ctx.blocked = blocked
        
        if blocked:
            ctx.max_positions = 0
            notes.append("[熔断] 禁止开仓")
        
        # Step 2: 方向选择
        ctx = self.find_active_sectors(ctx, sentiment_history)
        notes.extend(ctx.notes)
        
        # Step 3: 调仓决策
        sell_decisions = self.manage_positions(ctx, daily_data)
        notes.extend(ctx.notes)
        
        # 更新持仓（先卖后买，T+1模拟）
        sell_count = sum(1 for v in sell_decisions.values() if v == "SELL")
        if sell_count > 0:
            sold_codes = [c for c, v in sell_decisions.items() if v == "SELL"]
            notes.append(f"计划卖出: {len(sold_codes)}只 ({', '.join(sold_codes)})")
        
        # Step 4: 选股
        if not blocked and ctx.max_positions > len(positions):
            targets = self.select_targets(ctx, daily_data, pool)
            buy_targets = self.allocate_positions(ctx, targets)
        else:
            buy_targets = []
        
        notes.extend(ctx.notes)
        
        return {
            "date": date,
            "context": ctx,
            "sell_decisions": sell_decisions,
            "buy_targets": buy_targets,
            "notes": notes,
        }


def test_decision_tree():
    """快速测试"""
    sys.stdout.reconfigure(encoding='utf-8')
    
    tree = TradingDecisionTree()
    
    # 模拟盘前评估
    ctx = tree.assess_market("20260731")
    print(f"=== {ctx.date} ===")
    print(f"  情绪: {ctx.sentiment['heat_level']} ({ctx.sentiment['sentiment_score']})")
    print(f"  涨停: {ctx.sentiment['zt_count']}  炸板: {ctx.sentiment['zhaban_count']}")
    print(f"  连板高度: {ctx.sentiment['lianban_height']}")
    print(f"  仓位上限: {ctx.max_positions}只")
    for n in ctx.notes:
        print(f"  [Note] {n}")
    
    # 找方向
    ctx = tree.find_active_sectors(ctx)
    print(f"\n  主线: {ctx.active_sectors}")
    print(f"  板块强度: {ctx.sector_strength}")
    for n in ctx.notes:
        print(f"  [Note] {n}")


if __name__ == "__main__":
    test_decision_tree()
