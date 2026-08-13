# 外围市场因子模块补完记录

**日期：** 2026-08-02
**任务：** 补充美股等外围市场对A股的影响因子

## 背景
Brunson指出美股对A股影响重要，需要纳入模型。之前版本完全没有外围市场数据。

## 新增内容

### 1. overseas.py 因子模块（6个因子）
- **USMarketImpact**: 美股隔夜涨跌 → A股次日开盘情绪
- **USVolatilityRegime**: 美股自身波动率状态（高波动=情绪传染强）
- **HKMarketImpact**: 港股隔夜涨跌影响
- **GlobalRiskAppetite**: 综合美股+港股的全球风险偏好
- **OvernightSignal**: 隔夜信号综合因子（美股40%+港股30%+A50期货30%）
- **ForeignCapitalFlow**: 北向资金流入（外资直接投票）

### 2. 市场状态判断增强
三种市场状态的因子权重都加入了外围因子：
- BULL: us_market_impact(0.10) + overnight_signal(0.08) + north_flow_5(0.07)
- BEAR: us_market_impact(0.12) + overnight_signal(0.10) + north_flow_5(-0.08) ← 外资流出是风险信号
- SHOCK: us_market_impact(0.08) + overnight_signal(0.07) + north_flow_5(0.05)

### 3. data_loader增强
- get_us_index(): 获取美股指数（标普500/道琼斯/纳斯达克）
- get_hk_index(): 获取港股指数（恒生指数）
- get_global_overview(): 外围市场全景概览

### 4. main.py新增命令
- `python main.py overseas`: 查看外围市场最新涨跌+对A股影响判断

### 5. 毛选原则更新
- 调查研究：加入外围市场检查
- 敌进我退：加入美股暴跌降仓、北向流出防范

## 影响逻辑设计
```
美股隔夜涨跌 (权重40%)
    ↓
港股涨跌 (权重30%) ──→ 综合信号 ──→ A股次日开盘方向判断
    ↓                                        ↓
北向资金流向 (权重30%) ───────────→ 仓位调整
```

## AKShare接口
- 美股指数: `ak.index_global_hist_em(symbol='标普500')`
- 港股指数: `ak.stock_hk_index_daily_em(symbol='恒生指数')`
- 注意：东方财富API凌晨不稳定，白天正常

## 验证状态
- 代码逻辑完整 ✅
- AKShare接口名已修正 ✅
- 凌晨API连接不稳定（已知问题，白天可正常获取）⚠️
- 待白天验证完整数据拉取
