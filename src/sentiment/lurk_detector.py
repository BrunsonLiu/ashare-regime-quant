"""
lurk_detector.py - 中长线埋伏信号检测器

核心理念（散户埋伏逻辑）：
  不是抄底，是找"即将发生但还没被定价"的位置。
  上游资源股在大资金动手之前往往缩量横盘——这是主力建仓的脚印。

检测逻辑（4个维度，全部满足才算"可埋伏"）：
  1. 低位确认：股价处于近1年相对低位（距高点回撤够深，但非持续阴跌）
  2. 缩量止跌：近期成交量萎缩到地量（无人关注 = 洗盘尾声）
  3. 横盘企稳：近N周在窄幅区间横盘，不再创新低（底部形态）
  4. 催化逻辑：属于产业链上游（有未来需求逻辑，非纯概念）

买入时机（两种）：
  A. 左侧埋伏：缩量横盘期低吸（更早，但可能要等）
  B. 右侧确认：横盘后第一根放量阳线（主力启动信号，更稳）

卖出条件：
  - 涨幅30-50% → 止盈（不赚最后一个铜板）
  - 拿2个月还没动静 → 逻辑可能错，认输出
  - 跌破横盘区间下沿 → 止损
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from src.sentiment.supply_chain import THEME_CHAIN, get_theme_by_code, DEFENSIVE_SECTORS


class LurkDetector:
    """中长线埋伏检测器"""

    def __init__(self, config: Dict = None):
        self.cfg = config or {}
        # 检测参数
        self.high_lookback = 250        # 近1年高点回看（约250交易日）
        self.low_consolidation_days = 20  # 横盘企稳判定窗口
        self.volume_shrink_days = 10    # 缩量判定窗口
        self.volume_shrink_ratio = 0.45  # 缩量阈值：5日均量/60日均量 < 0.45 才算真缩量
        self.bottom_range_pct = 0.12    # 横盘区间宽度（12%以内算窄幅）
        self.far_from_high_pct = 0.25   # 距高点回撤至少25%
        self.recent_new_low_ok = 5      # 近5日内不再创新低
        # 新增：跌透判定（60日跌幅趋平，说明下跌动能耗尽）
        self.stop_falling_threshold = -0.06  # 近60日跌幅 > -6% 视为"还在跌"，不埋

        # 买入/卖出参数
        self.take_profit_pct = 0.35     # 埋伏止盈35%
        self.time_stop_days = 60        # 2个月没动静就出
        self.breakdown_stop_pct = -0.08 # 跌破横盘下沿8%止损

    # ==================== 核心检测 ====================

    def detect_low_position(self, code: str, name: str,
                            daily_df: pd.DataFrame) -> Dict:
        """
        检测单只股票是否处于"可埋伏"的低位状态

        返回:
        {
            "code": str,
            "name": str,
            "eligible": bool,           # 是否符合埋伏条件
            "score": int,               # 埋伏评分 0-10
            "signals": [str],           # 触发的信号说明
            "position_state": str,      # 位置状态: LOW/HIGH/MID
            "volume_state": str,        # 量能状态: SHRINK/EXPAND/NORMAL
            "consolidating": bool,      # 是否横盘企稳
            "buy_mode": str,            # 买入方式: left(左侧)/right(右侧)/none
            "stop_price": float,        # 建议止损价（横盘下沿）
            "target_price": float,      # 建议止盈价
        }
        """
        if daily_df is None or len(daily_df) < 60:
            return self._empty_result(code, name, "数据不足")

        df = daily_df.sort_values('date').reset_index(drop=True)
        close = df['close']
        volume = df['volume']
        high = df['high']

        # ============ 1. 位置判断 ============
        # 近1年高点
        window = df.tail(self.high_lookback)
        high_price = window['high'].max()
        current_price = close.iloc[-1]

        # 距高点回撤
        drawdown_from_high = (current_price - high_price) / high_price
        position_state = self._position_state(drawdown_from_high)

        # 新增：跌透判定（近60日跌幅趋平）
        # 赢家特征：买入前60日跌幅仅-3%（已止跌）；输家：-9%~-14%（还在跌）
        chg60 = 0.0
        if len(close) >= 60:
            chg60 = (current_price / close.iloc[-60] - 1)
        stop_falling = chg60 > self.stop_falling_threshold  # 60日跌幅 > -6% = 已跌透

        # ============ 2. 缩量判断 ============
        # 核心：近期量 vs 较长基准量（含前期下跌的高量能）
        # 用 5日均量 / 60日均量，横盘期5日量远低于60日基准 → 真缩量
        vol_ma5 = volume.rolling(5).mean()
        vol_ma60 = volume.rolling(60).mean()
        recent_vol_ma5 = vol_ma5.iloc[-1]

        if pd.notna(vol_ma60.iloc[-1]) and vol_ma60.iloc[-1] > 0:
            vol_ratio = recent_vol_ma5 / vol_ma60.iloc[-1]
        elif pd.notna(vol_ma5.iloc[-1]) and vol_ma5.iloc[-1] > 0:
            vol_ratio = recent_vol_ma5 / volume.rolling(20).mean().iloc[-1]
        else:
            vol_ratio = 1.0

        if vol_ratio < self.volume_shrink_ratio:
            volume_state = "SHRINK"
        elif vol_ratio > 1.5:
            volume_state = "EXPAND"
        else:
            volume_state = "NORMAL"

        # ============ 3. 横盘企稳判断 ============
        # 近20日价格区间
        recent = df.tail(self.low_consolidation_days)
        recent_high = recent['high'].max()
        recent_low = recent['low'].min()
        range_width = (recent_high - recent_low) / recent_low

        consolidating = range_width < self.bottom_range_pct

        # 近5日是否创新低
        recent5_low = df.tail(5)['low'].min()
        prev_low = df.tail(self.low_consolidation_days).head(self.low_consolidation_days - 5)['low'].min()
        no_new_low = recent5_low >= prev_low * 0.99  # 近5日没有明显新低

        # ============ 4. 右侧确认（主力启动信号）============
        # 数据验证（70次样本）：低位+跌透+放量阳线，60日均+21.9%胜率67%
        # 关键：不要"突破20日高"（假突破陷阱，60日胜率仅40%）
        #      也不要"大涨>3%"（被妖股拉高均值，中位仅+0.4%不稳）
        # 正确：放量（>5日均1.5倍）+ 阳线（涨>1%）就是启动脚印
        buy_mode = "none"
        if len(df) >= 2:
            today_vol = volume.iloc[-1]
            vol_ma5 = volume.rolling(5).mean().iloc[-1]
            today_chg = (close.iloc[-1] / close.iloc[-2] - 1)

            # 放量阳线：量 > 5日均1.5倍 且 涨>1%
            volume_surge = today_vol > vol_ma5 * 1.5 if pd.notna(vol_ma5) and vol_ma5 > 0 else False

            if volume_surge and today_chg > 0.01:
                buy_mode = "right"  # 右侧：主力放量启动
            # 左侧低吸已放弃（数据证伪：-3.3%负期望）

        # ============ 评分 ============
        score = 0
        signals = []

        # 位置分（0-3）
        if position_state == "LOW":
            score += 3
            signals.append(f"低位(距高点{drawdown_from_high:.0%})")
        elif position_state == "MID":
            score += 1
            signals.append(f"中位(距高点{drawdown_from_high:.0%})")
        else:
            signals.append(f"高位(距高点{drawdown_from_high:.0%})")

        # 跌透分（0-2）
        if stop_falling:
            score += 2
            signals.append(f"已跌透(60日{chg60:+.1%})")
        else:
            signals.append(f"仍在跌(60日{chg60:+.1%})")

        # 缩量分（0-3）
        if volume_state == "SHRINK":
            score += 3
            signals.append(f"缩量(量比{vol_ratio:.2f})")
        elif volume_state == "NORMAL":
            score += 1
        else:
            signals.append("放量")

        # 横盘分（0-2）
        if consolidating:
            score += 2
            signals.append(f"横盘企稳(区间{range_width:.1%})")

        # 无新低分（0-2）
        if no_new_low:
            score += 2
            signals.append("底部不再创新低")
        else:
            signals.append("仍在创新低")

        # ============ 判定 ============
        # 埋伏条件：低位 + 跌透 + 缩量 + 横盘 + 无新低（score >= 8 且已止跌）
        eligible = score >= 8 and position_state == "LOW" and stop_falling

        # 止损/止盈价
        stop_price = recent_low * (1 + self.breakdown_stop_pct)  # 横盘下沿再留8%缓冲
        target_price = current_price * (1 + self.take_profit_pct)

        return {
            "code": code,
            "name": name,
            "eligible": eligible,
            "score": score,
            "signals": signals,
            "position_state": position_state,
            "volume_state": volume_state,
            "consolidating": consolidating,
            "buy_mode": buy_mode,
            "stop_price": round(stop_price, 2),
            "target_price": round(target_price, 2),
            "drawdown_from_high": round(drawdown_from_high, 3),
            "vol_ratio": round(vol_ratio, 2),
            "range_width": round(range_width, 3),
            "current_price": round(current_price, 2),
            "chg60": round(chg60, 3),
            "stop_falling": stop_falling,
        }

    def _position_state(self, drawdown_from_high: float) -> str:
        """位置状态判定"""
        if drawdown_from_high <= -self.far_from_high_pct:
            return "LOW"
        elif drawdown_from_high <= -0.05:
            return "MID"
        else:
            return "HIGH"

    def _empty_result(self, code, name, reason) -> Dict:
        return {
            "code": code, "name": name, "eligible": False, "score": 0,
            "signals": [reason], "position_state": "N/A",
            "volume_state": "N/A", "consolidating": False,
            "buy_mode": "none", "stop_price": 0, "target_price": 0,
            "drawdown_from_high": 0, "vol_ratio": 0, "range_width": 0,
            "current_price": 0, "chg60": 0, "stop_falling": False,
        }

    # ==================== 批量扫描 ====================

    def scan_upstream_pool(self, daily_data: Dict[str, pd.DataFrame],
                           board_filter=("60", "00")) -> pd.DataFrame:
        """
        扫描全部产业链上游标的，返回埋伏候选清单

        参数:
            daily_data: {code: DataFrame[date, open, high, low, close, volume, ...]}
        返回: DataFrame 按评分降序
        """
        from src.sentiment.supply_chain import get_all_upstream_stocks

        upstream = get_all_upstream_stocks(board_filter)
        results = []

        for s in upstream:
            code = s["code"]
            if code not in daily_data:
                continue
            df = daily_data[code]
            r = self.detect_low_position(code, s["name"], df)
            # 附加产业链信息
            themes = get_theme_by_code(code)
            r["stage"] = s["stage"]
            r["themes"] = ",".join(t["theme"] for t in themes)
            results.append(r)

        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.sort_values("score", ascending=False)
        return df

    # ==================== 持仓管理（中线）====================

    def check_swing_exit(self, position: Dict, current_price: float,
                         days_held: int) -> Tuple[bool, str]:
        """
        中线埋伏的卖出检查

        参数:
            position: {cost, buy_date, ...}
            current_price: 现价
            days_held: 持有天数
        返回: (should_sell, reason)
        """
        cost = position["cost"]
        pnl_pct = (current_price / cost - 1)

        # 1. 止盈：涨35%就出
        if pnl_pct >= self.take_profit_pct:
            return True, f"埋伏止盈{pnl_pct:.1%}"

        # 2. 时间止损：2个月没动静
        if days_held >= self.time_stop_days and pnl_pct < 0.10:
            return True, f"埋伏{self.time_stop_days}天不涨"

        # 3. 跌破止损（横盘下沿）
        if "stop_price" in position and current_price < position["stop_price"]:
            return True, f"跌破横盘下沿{current_price:.2f}<{position['stop_price']:.2f}"

        # 4. 移动止盈：涨20%后回撤8%出
        if pnl_pct >= 0.20:
            peak = position.get("peak", cost)
            if current_price < peak * 0.92:
                return True, f"移动止盈{pnl_pct:.1%}"

        return False, ""


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # 加载几只上游票测试
    import pandas as pd
    from config import DAILY_DIR

    test_codes = ["601899", "600362", "000630", "600219", "000970", "600111"]

    detector = LurkDetector()
    print("=== 埋伏检测测试 ===\n")
    for code in test_codes:
        path = os.path.join(DAILY_DIR, f"{code}.csv")
        if not os.path.exists(path):
            print(f"  [{code}] 无数据")
            continue
        df = pd.read_csv(path)
        r = detector.detect_low_position(code, code, df)
        status = "符合" if r["eligible"] else "不符合"
        print(f"  [{code}] {status} | 评分={r['score']}/10 | {r['position_state']}/{r['volume_state']}")
        print(f"     回撤={r['drawdown_from_high']:.1%} 量比={r['vol_ratio']} 区间宽={r['range_width']:.1%}")
        print(f"     信号: {'; '.join(r['signals'])}")
        if r["buy_mode"] != "none":
            print(f"     >> 买入方式: {r['buy_mode']}  止损{r['stop_price']} 止盈{r['target_price']}")
        print()
