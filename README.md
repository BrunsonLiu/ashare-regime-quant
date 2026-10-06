# A股量化交易系统（毛选版）

## 项目定位
个人散户量化交易系统，针对 A 股市场特性设计。
**不做高频 / 纯数学量化**，核心是「A股交易守则」+ 多因子选股 + 市场状态自适应仓位 + 情绪周期决策。
全免费数据源（Baostock 为主、AKShare/东财为辅）。

## 核心思想（毛选落地）
- **实事求是**：因子横截面 z-score 标准化，消除量纲；具体问题具体分析，策略随市场变化迭代
- **调查研究**：每交易日先判市场状态（牛 / 震 / 熊），再定仓位与因子权重
- **集中优势兵力**：分位数筛选，前 20% 买、后 20% 卖，不撒胡椒面
- **抓主要矛盾**：不同市场状态用不同因子权重表

## 市场状态判断（4 维度 + 慢牛专项，政策偏置已关闭）
- **BULL（牛市）**：满仓干，5 只，单只 25%；动量/均线排列/量价背离权重高
- **SHOCK（震荡/慢牛）**：轻仓试探，3 只，单只 20%；反转因子为主
- **BEAR（熊市）**：**空仓观望**（或极低仓位 1 只 15%）；保存实力，时刻留意市场
- **慢牛结构专项**：120 日高点回撤 <15% 且 60 日低点抬升 ≥3% 且均线未死叉且近 20 日跌幅不深 → 给牛市加分
（段3 亏 46% 教训：只看位置不看趋势，把见顶下跌误判成慢牛回调；已加趋势确认关；
 数据不足 120 日时该维度显式停用，不再静默失效）
- **政策偏置**：已关闭（bias=0），政策数据不可控，不让人工判断翻盘技术面

## 因子体系（横截面 z-score 后按状态加权）
- 量价(7)：动量 / 反转 / 波动率 / 换手 / 均线排列 / Amihud 非流动性 / 量价背离
- 情绪(3)：涨停计数 / 换手异动 / 跳空
- 基本面(5)：PE / PB / ROE / 营收代理增速 / 市值 / 景气度 / 行业轮动
- 外围(3)：美股隔夜影响 / 全球风险偏好 / 隔夜信号综合
- 已移除死权重 `north_flow_5`：个股K线无北向数据，因子恒 0 占位；接入真实北向数据后再启用
- 注意：`revenue_growth`/`prosperity` 中的 roe/revenue 目前是日线代理序列，`pct_change(4)`
  是近 4 个交易日变化而**非财报同比**，接入季度财务数据后语义自动升级

## 回测方法论（2026-10-06 审查后口径，务必阅读）
修复前引擎存在**系统性前视偏差**（当日收盘决策、当日开盘成交），历史回测结果不可信。
当前引擎的时序契约：

```
T-1 收盘 ──→ 因子/信号/状态/止损止盈判断 ──→ T 日开盘价 ± 滑点成交 ──→ T 收盘仅用于盯市
```

- 信号：`date=T` 的信号由**严格早于 T** 的数据算出（`multi_factor.backtest_with_regime`）
- 涨跌停：昨收由 `pre_close 列 → pctChg 反推 → 前一根收盘` 三级回退；创业板/科创板 20%，
  主板 10%；开盘封死涨停买不进、封死跌停卖不出，成交价不越过涨跌停价
- 停牌：持仓按最近有效收盘估值（不再按 0 元计入净值造成假回撤/假熔断）
- 组合风控：-8% 熔断清仓 + 10 日冷却；BEAR/指数破位清仓；连亏 3 次降仓、连亏 5 次
  暂停开仓 **10 个交易日后自动恢复**（避免无持仓时永久死锁）
- 仓位：以**组合总资产**（现金+持仓市值）为基准计算，且有现金充足性校验

## 情绪周期子系统（src/sentiment/）
- **数据管线**：`rebuild_scheduler`（外层调度，断点续传+失败重试+超时放弃）→
  `rebuild_worker`（内层 baostock 抓取，**前复权**判定涨停/炸板，行缓冲落盘）→
  `aggregate_sentiment`（聚合去重出 sentiment_3y.csv）
- **决策树** `decision_tree.py`：盘前情绪评估 → 炸板率修正**只降温不升温**（冰点日绝不升仓）
  → 板块主线（排除防御板块）→ 龙头优先选股 → 仓位分配
- **埋伏检测** `lurk_detector.py`：低位+缩量+横盘企稳，右侧确认=量>前5日均量1.5倍+涨>1%
- **采集器** `market_sentiment.py`：涨停池/炸板池/龙虎榜/北向；接口故障与"真实冰点"
  严格区分，故障日不冒充冰点

## Web 终端（web/）
纯静态前端 + `web/data/*.json` 数据包，深色金融终端风格，7 个页面：

| 页面 | 内容 |
|---|---|
| index.html | 情绪终端：总览/周期分析/回测绩效/交易流水/滚动验证 5 个 tab |
| regime.html | 市场状态：BULL/SHOCK/BEAR 历史时间线与当前建议 |
| live.html | 实时概览：指数/板块/涨停 TOP20/主力资金 |
| overseas.html | 外围市场：标普500/恒生/美元指数 + 综合判断 |
| signals.html | 交易信号（需先 `main.py signal`） |
| factors.html | 因子 IC/IR 与分组收益 |
| principles.html | 毛选原则 ↔ 代码模块映射 |

```bash
python main.py gen-webdata   # 生成全量 JSON 数据包（web/data/）
python main.py serve-web     # http://localhost:8899
python main.py dashboard     # 上面两步连做
```
数据 JSON 全部经过 NaN 安全序列化（浏览器 `JSON.parse` 严格合法）。

## 交易守则
详见 `A股交易守则.md`（四环境打法：牛市 / 震荡 / 熊市 / 极端）。

## 项目结构
```
quant_a_share/
├── README.md                 # 项目说明
├── config.py                 # 全局配置（POOL/DATA/TRADE/REGIME/RISK/FACTOR/POLICY/PORTFOLIO_RISK）
├── main.py                   # 入口（14 个子命令，见下）
├── A股交易守则.md             # 四环境交易守则
├── data/                     # 数据存储（daily/*.csv 不入库，其余随仓库）
├── src/
│   ├── data_loader.py        # 数据下载与缓存（Baostock 主 / AKShare 备）
│   ├── stock_pool.py         # 股票池过滤（排除ST/退市/北交所）
│   ├── direct_data.py        # 东财裸 HTTP 实时数据（指数/涨跌停池/板块/资金流）
│   ├── visualize.py          # plotly 交互式 HTML 报告（data/results/）
│   ├── serve_web.py          # web 静态服务（8899）
│   ├── factors/              # 因子库（base/price_volume/sentiment/fundamental/money_flow/overseas）
│   ├── sentiment/            # 情绪子系统（见上节）
│   ├── backtest/             # engine / swing_backtest / factor_analysis
│   ├── strategy/             # multi_factor.py
│   └── utils/                # market_regime / position_manager / mao_principles
├── web/                      # 前端（html/js/css + data/*.json）
├── tests/                    # 单元测试（python -m pytest tests/ -v）
└── notebooks/                # 探索性分析
```

## 使用方法（全部子命令）
```bash
python main.py pool         # 构建股票池
python main.py data         # 下载日线数据（Baostock，含缓存）
python main.py regime       # 查看当前市场状态与仓位建议
python main.py live         # 实时概览（涨跌停池/板块/指数）
python main.py signal       # 生成交易信号（data/latest_signals.csv）
python main.py backtest     # 运行回测（equity/trades CSV）
python main.py walkforward  # walk-forward 分段滚动验证
python main.py factors      # 因子 IC/IR 分析（动量示例）
python main.py principles   # 毛选原则映射
python main.py overseas     # 外围市场快照
python main.py report       # 可视化报告 HTML（data/results/）
python main.py gen-webdata  # 生成前端 JSON 数据包
python main.py serve-web    # 启动 Web 终端（localhost:8899）
python main.py dashboard    # gen-webdata + serve-web
```

## 测试
```bash
python -m pytest tests/ -v          # 全部单元测试
python -m unittest discover tests   # 无 pytest 时用 stdlib
```
覆盖：回测引擎时序契约（涨跌停/现金/T+1/停牌估值/状态重置）、决策树降温方向、
仓位管理冷却与 sizing、市场状态守卫、因子除零与外围对齐、NaN 安全序列化、
direct_data 的 secid/涨跌停池解析。
akshare/baostock 缺失时测试自动注入 stub，不依赖网络。

## 回测结果（2026-10-06，修复后引擎真实口径）
> 2026-10-06 审查修复了前视偏差（当日收盘决策/当日开盘成交）与涨跌停保护失效，
> 下表为**修复后引擎**的重跑结果——旧引擎的 +12.14% 属于前视偏差美化，已作废。

| 指标 | 数值（样本内 2025-11-25 ~ 2026-07-31，主板流动性前 800 只） |
|------|------|
| 总收益率 | **-2.15%**（期末 97,845） |
| 最大回撤 | **-11.44%** |
| 夏普比率 | -0.18 |
| 胜率 | 57.1% |
| 盈亏比 | 0.65 |
| 卖出交易 | 21 次 |

**Walk-Forward（3 段，修复后口径）**

| 段 | 区间 | 收益 | 最大回撤 | 夏普 | 胜率 | 交易 |
|---|---|---|---|---|---|---|
| 1 | 2026-05-28 ~ 2026-07-09 | -0.46% | -13.42% | 0.15 | 45.8% | 48 |
| 2 | 2026-07-10 ~ 2026-08-19 | -6.29% | -6.88% | -3.82 | 33.3% | 21 |
| 3 | 2026-08-20 ~ 2026-09-30 | +0.00%（无交易†） | 0.00% | — | — | 0 |

† 段3 无交易：日线缓存止于 2026-08-13 而指数到 9 月底，刷新 `python main.py data` 后重跑才有意义。

**结论（实事求是）**：修复时序契约后，当前因子体系在样本内**没有正期望**（0/3 段正收益，
回撤 -11.44% 远超熔断阈值 -8% 说明熔断机制实际会频繁介入）。旧引擎 +12% 的"稳健盈利"
是买在信号日开盘、用信号日收盘决策的系统性美化。下一步应优先改进因子与风控参数，
而不是沿用旧回测结论。

> ⚠ 样本内 + 短窗口滚动验证，不代表未来收益。

## 关键修复记录
- 2026-10-06 全面审查（50 项）：
  - **回测前视偏差**：T-1 收盘决策、T 开盘成交；涨跌停保护从"恒 False"到三级昨收回退
  - **决策树方向反转**：炸板率>35% 曾把冰点日升成 WARM（`max(0,score-1)` 反向钳位）
  - **前端 NaN 瘫痪**：SafeJSONEncoder 对 float NaN 无效 → trades/regime.json 非法 JSON
  - **深市指数 secid 硬编码**：399xxx 永远拿不到；"涨停"实为涨幅排行 → 东财涨停池
  - 龙虎榜 API 参数错误、rebuild 管线静默丢股票、watcher 误触发、美股因子数万次重复请求等
  - 详见该次提交信息
- 更早：因子权重 key 错配 / 横截面 z-score / 分位数选股 / 净值曲线起点（见 git log）

## 风险与局限
- **当前因子体系在修复后口径下无正期望**（见上），需改进因子/风控后再评估
- 段3 无交易：日线缓存止于 2026-08-13，先 `python main.py data` 刷新再回测
- 3 年涨停事件数据为不复权口径构建，`rebuild_worker` 已改前复权；
  口径统一需删除 `data/zt_done.txt` 全量重跑（4400 只 × 3 年，耗时较长）
- 北向资金因子未接入真实数据（权重表已移除）；港股影响未接入
- roe/revenue 为日线代理，非财报数据
- 创业板 / 科创板已排除（主板为主）；滑点/涨跌停为简化模型
- 情绪数据源（东财）受网络环境影响，接口故障会被显式标记而非静默降级

## 开发进度
- [x] 数据管线 / 股票池 / 因子框架 / 回测引擎 / 策略
- [x] 市场状态判断（慢牛专项）
- [x] 横截面 z-score + 分位数集中选股
- [x] 可视化报告（plotly 交互式 HTML 仪表盘）
- [x] walk-forward 滚动验证
- [x] 情绪周期子系统（3 年数据落库 + 决策树 + 埋伏检测）
- [x] Web 终端（7 页面 + 数据包生成器）
- [x] 单元测试套件（53 个，CI 自动运行）
- [x] 2026-10-06 全面审查修复（回测时序契约重建）+ 修复后重跑回测/walk-forward
- [ ] 改进因子与风控，使修复后口径下出现正期望
- [ ] 日线数据刷新后重跑段3
- [ ] 涨停事件数据前复权口径全量重建
- [ ] 接入真实北向/港股/季度财务数据
- [ ] 因子 IC/IR 实盘验证
