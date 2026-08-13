# A股量化系统 - 项目记录

**日期：** 2026-08-01 ~ 2026-08-02
**项目路径：** D:\desktop2\quant_a_share

## 目标
为Brunson搭建个人散户A股量化交易系统，毛选思想驱动，全免费数据源。

## 核心设计原则
- 资金量小，灵活进出
- 找主线，跟景气度
- ST不碰，纯炒作不碰，没人玩的不碰
- 策略随市场变化迭代（毛选思想：实事求是、具体问题具体分析）

## 毛选思想体系（8大原则 → 代码落地）
1. **实事求是** → 一切从数据出发，回测验证
2. **矛盾论/抓主要矛盾** → 不同市场状态用不同因子权重
3. **实践论** → 因子IC/IR分析，失效淘汰
4. **游击战十六字诀** → 仓位管理（敌进我退/敌驻我扰/敌疲我打/敌退我追）
5. **集中优势兵力** → 最多5只，信号强的优先
6. **持久战** → 连续亏损自动降仓冷却
7. **调查研究** → 买入前三重验证（基本面+资金面+技术面）
8. **战略藐视战术重视** → 长期乐观+每笔严格止损

## 项目结构（17个文件，~75KB代码）
```
quant_a_share/
├── main.py                    # 入口：pool/data/regime/signal/backtest/factors/principles
├── config.py                  # 全局配置（股票池/交易/风控/因子参数）
├── data/
│   ├── stock_pool.csv         # 股票池（4400只）
│   └── daily/                 # 日线数据缓存
├── src/
│   ├── data_loader.py         # AKShare数据加载（日线/指数/北向/龙虎榜）
│   ├── stock_pool.py          # 股票池过滤（ST/退市/流动性/板块）
│   ├── factors/
│   │   ├── base.py            # 因子基类 + 计算引擎
│   │   ├── price_volume.py    # 量价因子（7个）
│   │   ├── money_flow.py      # 资金面因子（4个）
│   │   ├── sentiment.py       # 情绪因子（3个）
│   │   └── fundamental.py     # 基本面+景气度因子（6个）
│   ├── backtest/
│   │   ├── engine.py          # T+1回测引擎（止损止盈/仓位管理/涨跌停）
│   │   └── factor_analysis.py # 因子IC/IR/分组收益分析
│   ├── strategy/
│   │   └── multi_factor.py    # 多因子选股（状态自适应+信号生成+回测）
│   └── utils/
│       ├── mao_principles.py  # 毛选思想体系映射
│       ├── market_regime.py   # 市场状态判断+仓位建议
│       └── position_manager.py # 仓位管理+止损止盈+连续亏损冷却
```

## 因子库（20个因子）
### 量价因子（7个）
- Momentum(20) 动量
- Reversal(5) 反转
- Volatility(20) 波动率
- Turnover(5) 换手率
- MAAlign(5,20,60) 均线排列
- AmihudIlliquidity(20) 非流动性
- AmountRatio(20) 量比

### 情绪因子（3个）
- TurnoverSpike(20) 换手率异动
- PriceGap 跳空缺口
- LimitUpCount 涨停连板

### 基本面因子（6个）
- PE 市盈率
- PB 市净率
- ROE 净资产收益率
- RevenueGrowth 营收增速
- MarketCap 市值
- ProsperityFactor 景气度（核心，你说的"看景气度"）
- IndustryRotation 行业轮动（核心，你说的"找主线"）

### 资金面因子（4个，部分待接入数据）
- MainMoneyFlow 主力净流入
- NorthHoldingChange 北向资金
- BigOrderNetInflow 大单净流入
- AmountRatio 量比

## 市场状态判断（多维度）
- MA均线排列 + 波动率 + 近期涨跌 + 量价配合
- 三状态：BULL/BEAR/SHOCK
- 自动切换因子权重 + 仓位建议

## 仓位管理（敌进我退）
- BULL → 最多5只，最大仓位100%
- SHOCK → 最多3只，最大仓位60%
- BEAR → 最多1只，最大仓位20%
- 连续亏损3次 → 冷却期降仓
- 止损7% / 止盈15% / 移动止盈5%

## 验证结果
1. **股票池构建** ✅ 5534→4400只
2. **市场状态判断** ✅ 当前BEAR（空头），仓位建议降至20%
3. **毛选原则** ✅ 8大原则全部映射到代码

## 待完成
- [ ] 下载全量日线数据（凌晨数据源不稳定）
- [ ] 生成交易信号验证
- [ ] 回测引擎完整跑通
- [ ] 接入个股资金流数据
- [ ] 接入北向资金数据
- [ ] 行业分类数据（支撑行业轮动因子）
- [ ] walk-forward滚动验证

## 技术栈
- Python 3.11.10
- AKShare 1.18.81
- pandas 3.0.3 / numpy 2.4.6
