"""
全局配置
"""
import os

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 数据目录
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DAILY_DIR = os.path.join(DATA_DIR, "daily")
FACTOR_DIR = os.path.join(DATA_DIR, "factors")
RESULT_DIR = os.path.join(DATA_DIR, "results")

# 创建目录
for d in [DATA_DIR, DAILY_DIR, FACTOR_DIR, RESULT_DIR]:
    os.makedirs(d, exist_ok=True)

# === 股票池过滤条件 ===
POOL_CONFIG = {
    "exclude_st": True,           # 排除ST（你说ST不碰）
    "exclude_delisting": True,    # 排除退市
    "exclude_bj": True,           # 排除北交所
    "min_amount": 1e7,            # 最低日成交额1000万（没人玩的不碰）
    "min_market_cap": 0,          # 最低市值（不限）
    "max_market_cap": 0,          # 最高市值（不限）
    "board_filter": ["60", "00"],  # 沪主板(sh.6xxx) / 深主板(sz.00xxx)；不做创业板(30xxx)/科创板(68xxx)
}

# === 数据参数 ===
DATA_CONFIG = {
    "history_days": 250,          # 默认拉取历史天数（约1年）
    "adjust": "qfq",              # 前复权
    "index_code": "000001",       # 默认上证指数
}

# === 交易参数 ===
TRADE_CONFIG = {
    "initial_capital": 100000,    # 初始资金10万（你说资金量小）
    "max_positions": 5,           # 最大持仓5只（集中优势兵力）
    "position_pct": 0.2,          # 单只仓位20%
    "commission_rate": 0.00025,   # 佣金万2.5
    "stamp_tax": 0.0005,          # 印花税千0.5（卖出）
    "slippage": 0.001,            # 滑点千1
}

# === 市场状态阈值 ===
REGIME_CONFIG = {
    "ma_short": 20,               # 短期均线
    "ma_long": 60,                # 长期均线
    "vol_window": 20,             # 波动率窗口
    "bull_vol_threshold": 0.012,  # 牛市波动率上限
    "bear_vol_threshold": 0.020,  # 熊市波动率下限
    "trend_threshold": 0.02,      # 趋势判断阈值2%
}

# === 止损止盈(中长线口径) ===
# 依据: src/backtest/risk_cadence_test.py(逐股T+1开盘成交, 含成本)——
#   -7%短线止损被正常波动打穿(茅台级龙头年波动±30%) +27.8% vs 放宽-15%的+31.9%
#   无止损则回撤偏大; 故中长线止损放宽到-15%
RISK_CONFIG = {
    "stop_loss": -0.15,           # 止损15%(中长线; 原-7%为短线口径)
    "take_profit": 0.0,           # 0=不止盈(中长线让利润奔跑, 守则第四章)
    "trailing_stop": 0.0,         # 0=不启用移动止盈
    "trailing_activate": 0.30,
    "max_consecutive_losses": 3,
    "trade_cooldown": 5,
    "rebalance_cadence": "monthly",  # 调仓节拍: 月频(逐日把收益磨在成本上)
}

# 交易参数(中长线): 调仓节拍默认月频
TRADE_CADENCE = {
    "rebalance_days": 20,         # 约1个月
}

# === 因子配置 ===
FACTOR_CONFIG = {
    # 基础因子周期
    "momentum_period": 20,
    "reversal_period": 5,
    "volatility_period": 20,
    "turnover_period": 5,
    # 均线
    "ma_short": 5,
    "ma_mid": 20,
    "ma_long": 60,
    # 信号阈值
    "buy_quantile": 0.80,         # 前20%买入
    "sell_quantile": 0.20,        # 后20%卖出
}

# === 政策偏置（结合政策/新闻，外部输入，实事求是）===
# bias: 1=政策偏多, 0=中性, -1=政策偏空
# 当前关闭：政策数据源不可控，避免人工 bias 翻盘技术面（2026-08-04）
POLICY_CONFIG = {
    "bias": 0,
    "note": "关闭政策偏置，纯技术面判断",
}

# === 组合级风控熔断 ===
PORTFOLIO_RISK_CONFIG = {
    "max_drawdown_cutoff": -0.08,   # 总资金回撤-8%强制清仓（散户保存实力）
    "cutoff_cooldown": 10,          # 熔断后空仓冷却10个交易日
    "index_break_stop_open": True,  # 指数破位停止开仓
    "index_break_threshold": -0.04, # 近20日指数跌幅超4%视为破位
    "bear_clear_positions": True,   # BEAR状态或指数破位时清仓观望
}
