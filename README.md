# A股行业龙头策略系统

> **一句话**：一个诚实的负结果 + 一套可复现的验证框架。
> 经五重检验，本项目**未发现稳定可交易的 alpha**；真正沉淀下来的是回测时序契约、
> 环境闸门风控、以及"哪些路已经走死"的负面清单。

面向 A 股主板的行业龙头策略系统。多因子选股 + 市场状态自适应仓位 + 情绪周期决策，
100% 免费数据源（Baostock 为主、AKShare / 东财为辅）。

**接手前请先读[策略结论](#策略结论必读)与[已知坑](#已知坑接手前必看)两节。**

---

## 目录

- [快速开始](#快速开始)
- [系统架构](#系统架构)
- [数据契约（不可违反）](#数据契约不可违反)
- [命令行参考](#命令行参考)
- [Web 终端](#web-终端)
- [策略结论（必读）](#策略结论必读)
- [已知坑（接手前必看）](#已知坑接手前必看)
- [测试](#测试)
- [项目结构](#项目结构)
- [开发路线](#开发路线)

---

## 快速开始

```bash
git clone https://github.com/BrunsonLiu/ashare-regime-quant.git
cd ashare-regime-quant

python -m venv .venv && . .venv/Scripts/activate     # Windows
pip install -r requirements.txt

# 先看数据现状（各数据集行数 / 新鲜度 / 契约健康）
python main.py manifest

# 跑一遍回测
python main.py backtest

# 起Web 终端
python main.py dashboard        # = gen-webdata + serve-web
# 浏览器打开 http://localhost:8899
```

**首次运行**需要先拉数据（约 98MB，不入库）：

```bash
python main.py pool             # 构建股票池
python main.py data             # 下载日线（耗时较长）
python main.py refresh          # 情绪数据增量 → 聚合 → 前端数据包
```

**环境**：Python 3.10 / 3.12（CI 双版本验证）。numpy 需 `<2.3`。

---

## 系统架构

```
数据层  Baostock(日线) + 东财(实时/涨停池/资金流) + 同花顺(行业)
   ↓
因子层  8 个已验证因子，横截面 z-score 标准化 → 按市场状态动态加权
   ↓
状态层  4 维市场状态判断（BULL / SHOCK / BEAR）+ 慢牛专项 + 守则四环境(A/B/C/D)
   ↓
策略层  分位数集中选股（前 20% 买）+ 环境闸门控仓 + 龙头池聚焦
   ↓
回测层  T-1 决策 / T 开盘成交 / 含费用 / T+1 / 涨跌停约束
   ↓
展示层  CLI + Plotly 报告 + Web 终端（8 页面）
```

### 因子体系

代码里有 30+ 个因子类，但 **IC 检验实际启用 8 个**（`web/data/factors.json` 为准）：

| 类别 | 已验证因子 |
|---|---|
| 量价 | `momentum_20` / `reversal_5` / `volatility_20` / `turnover_avg_5` / `ma_align_5_20_60` / `amihud_20` / `vol_price_div_20` |
| 情绪 | `turnover_spike_20` |

未进入权重表的（IC 不显著或无数据）：`pe` / `pb` / `roe` / `revenue_growth` /
`market_cap` / `prosperity` / `industry_rotation` / `us_market_impact` 等。

**因子权重按状态动态算**：不是硬编码权重表，而是
`src/backtest/regime_weights.py` 训练期算各因子 IC，按 `|IC| >= 0.015` 筛出有效因子，
`|w|` 归一化为 1（保留符号）——牛市用正 IC 因子，熊市自动翻成负 IC 因子。

**已知口径局限**：`revenue_growth` / `prosperity` 里的 roe / revenue 目前是
**日线代理序列**，`pct_change(4)` 是近 4 个交易日变化而**非财报同比**。
接入季度财务数据后语义自动升级。

### 市场状态判断

- **BULL（牛市）**：满仓，5 只，单只 25%
- **SHOCK（震荡）**：轻仓，3 只，单只 20%
- **BEAR（熊市）**：**空仓观望**，保存实力
- **慢牛专项**：120 日回撤 <15% + 60 日低点抬升 ≥3% + 均线未死叉 + 近 20 日跌幅不深
- **政策偏置**：已关闭（bias=0），不让不可控的人工判断翻盘技术面

慢牛专项的教训：段 3 亏 46%，因为只看位置不看趋势，把见顶下跌误判成慢牛回调，
现已加趋势确认关。数据不足 120 日时该维度**显式停用**，不静默失效。

---

## 数据契约（不可违反）

### 回测时序契约

```
T-1 收盘数据 ──→ 因子/信号/状态/止损判断 ──→ T 开盘价 ± 滑点成交 ──→ T 收盘仅盯市
```

- 因子必须**后视纯**：第 t 行只能由 ≤ t 的数据决定。全样本标准化 / 未来函数违反此契约
- 涨跌停：昨收三级回退（`pre_close` 列 → `pctChg` 反推 → 前一根收盘）；
  主板 10%，创业板/科创板 20%；开盘封死涨停买不进、封死跌停卖不出
- 停牌：按最近有效收盘估值，不归零
- T+1：买入当日不可卖出
- 仓位以**组合总资产**（现金 + 持仓市值）为基准，含现金充足性校验
- 风控：-8% 熔断清仓 + 10 日冷却；连亏 3 次降仓、连亏 5 次暂停开仓 **10 个交易日后自动恢复**

违反任一条，`tests/test_timing_contract.py` 与 `test_engine.py` 会失败。

### 前端数值口径

后端 JSON 有两类百分数字段，**混淆会导致 Y 轴量级差 100 倍**：

| 类型 | 例子 | 前端处理 |
|---|---|---|
| 已格式化的百分数字符串 | `factors.json` 的 `"IC胜率":"42.5%"` | `parseFloat` 后**直接用**，不要再 `*100` |
| 存小数的比例 | `sentiment.json` 的 `zhaban_rate: 0.375` | `*100` 转百分比 |

JSON 全部经 `sanitize_json` 处理，浏览器 `JSON.parse` 严格合法（无 NaN / Infinity 字面量）。

---

## 命令行参考

```bash
# 数据
python main.py pool             # 构建股票池（排除 ST/退市/北交所）
python main.py data             # 下载日线数据（含缓存）
python main.py manifest         # 数据世界观：行数/新鲜度/契约健康
python main.py refresh          # 一键更新到最新（情绪增量→聚合→数据包）

# 分析
python main.py regime           # 当前市场状态与仓位建议
python main.py live             # 实时概览（指数/板块/涨停池/资金流）
python main.py overseas         # 外围市场快照
python main.py signal           # 生成交易信号
python main.py daily            # 每日决策助手（环境+主线行业+龙头建议）
python main.py daily --hold 600519,000858   # 结合持仓给调仓提示
python main.py factors          # 因子 IC / IR 分析
python main.py principles       # 毛选原则 ↔ 代码模块映射

# 回测
python main.py backtest         # 运行回测
python main.py walkforward      # walk-forward 分段滚动验证

# 输出
python main.py report           # Plotly HTML 仪表盘（data/results/）
python main.py gen-webdata      # 生成前端 JSON 数据包
python main.py serve-web        # 启动 Web 终端（localhost:8899）
python main.py dashboard        # gen-webdata + serve-web
```

---

## Web 终端

纯静态前端，8 个页面，无构建步骤。数据来自 `web/data/*.json`。

| 页面 | 内容 |
|---|---|
| `index.html` | 情绪终端：总览 / 周期分析 / 回测绩效 / 交易流水 / 滚动验证（5 个页签） |
| `daily.html` | 每日决策：环境闸门 + 仓位上限 + 主线行业 + 候选龙头 + 模拟持仓 |
| `regime.html` | 市场状态：MA / 波动率 / 慢牛评分 / 仓位建议 |
| `live.html` | 实时概览：指数 / 板块涨跌 / 涨停 TOP20 / 主力资金 |
| `overseas.html` | 外围市场：标普500 / 日经 / KOSPI / 恒生 + 传导路径 |
| `signals.html` | 交易信号明细（**需先 `python main.py signal`**） |
| `factors.html` | 因子 IC / IR / 分组收益 |
| `principles.html` | 毛选原则 ↔ 代码模块映射 |

### 前端架构

`web/js/shared.js` 是**唯一真源**：导航配置、配色 `C`、Plotly 基座 `LAYOUT` /
`makePlot`、`DataLoader`、格式化函数、hash 路由、空状态兜底。

页面统一用法：

```html
<script src="js/shared.js"></script>
<script>renderLayout('pageKey');</script>
```

新增页面只需：在 `NAV_CONFIG` 加一项 + 引入 `shared.js` + 调`renderLayout()`。
**不要重新定义 `C` / `LAYOUT` / `makePlot`**，历史上就是这么漂移出不一致的。

配色已按 WCAG AA 校验（白底与页面底均 ≥ 4.5:1）：

| 变量 | 值 | 说明 |
|---|---|---|
| `--text-3` | `#646c78` | 次要说明文字 |
| `--up` | `#c92a2a` | 红涨（A 股约定） |
| `--down` | `#067d47` | 绿跌 |
| `--accent` | `#1b62c4` | 选中/链接 |
| `--text-4` | `#8a929d` | **仅装饰**，不承载信息 |

**KPI 状态色用左侧色条，不用红绿**——「涨停家数 68」是量纲不是涨跌。
真涨跌字段单独用 `.q-up` / `.q-down`。

---

## 策略结论（必读）

> 经全面严格复核，本项目**未发现任何稳定可交易的 alpha**。
> 系统的真正价值是"纪律与风险控制"，不是"跑赢市场"。
> 完整结论见 [`STRATEGY_CONCLUSION.md`](STRATEGY_CONCLUSION.md)。

**检验标准（五关）**：无前视 + 含成本 + 长样本(2014-2026) + 分段稳健 + 可执行。
**没有任何结论同时通过五关。**

### 被推翻的结论（如实记录）

| 曾经报出 | 真相 | 原因 |
|---|---|---|
| 19 因子 +12.14% | **-2.15%** | 前视偏差 |
| 龙头池优势 +92.6pp | **+35.5pp** | 选池前视 |
| 熊市空仓 +234% | **+55.7%，跑输持有** | 当日成交前视 + 零成本 |
| 只做 A +173% | **+55.8%，跑输持有** | 当日成交前视 + 零成本 |
| amihud 三重确认 | **只赢 1/4 段，段均 -11.95pp** | 单段复利假象 |
| 情绪轮动 +266% | **段 3 亏 -20%** | 单段运气 |

### 幸存的两个（都不是 alpha）

1. **龙头池 universe 优于全池**（PIT + 逐年滚动均成立）——"选对战场"
2. **环境闸门的风控价值**：只做 A 回撤 **-21.3%** vs 全程持有 **-64.4%**——"少亏工具"

### 为什么没有 alpha 不意外

- 公开量价数据里的稳定 alpha 早被抹平
- 交易成本是天敌（换手拖累实测 20~66%）
- 12 年 ≈ 2~3 个独立行情，统计上不足以区分真 edge 与运气

**系统正确定位**：纪律助手 + 风险仪表盘，**不是自动交易系统**。

**若继续找 alpha**：换数据（资金流/龙虎榜/财报）> 换频率（更低频）> 换品种（可转债/ETF）。
**不要再在免费日线量价上调参找因子——这条路已穷尽。**

### 情绪择时：已证伪，勿重复测试

`src/backtest/sentiment_timing.py` 检验"冰点反转"假说：

- 上证 / 沪深300 / 创业板指 × 六种变体，每笔中位收益**全部 ≈0 或为负**
- "持有 3 日"表面 +14.2%，但**全部利润来自单笔 2024-09-25 信号**（+26.5%）；
  去掉该笔后剩余 70 笔合计 **-12.2%**——是彩票不是 edge
- "连续 2 日冰点 = 更强洗盘"的直觉被证伪（胜率反而最低 18~31%）

**解读**：75% 的"冰点后 3 日涨停数回升"是情绪指标维度的恢复，**不构成价格优势**。
情绪数据的价值定位是**状态感知**，不是择时信号。

---

## 已知坑（接手前必看）

### 数据与口径

| 坑 | 说明 |
|---|---|
| 日线缓存止于 2026-08-13 | 段 3 回测无交易，需先 `python main.py data` 刷新 |
| 涨停事件数据口径不一致 | `zt_events.csv` 是不复权构建，`rebuild_worker` 已改前复权。口径统一需删 `data/zt_done.txt` 全量重跑（4400 只 × 3 年，耗时较长） |
| 北向资金未接入 | 权重表已移除，港股影响也未接入 |
| roe / revenue 是日线代理 | 非财报数据 |
| 创业板 / 科创板已排除 | 主板为主；滑点/涨跌停为简化模型 |
| 情绪数据源受网络影响 | 东财接口故障会被**显式标记**而非静默降级 |

### 工程

| 坑 | 说明 |
|---|---|
| **Plotly 已本地化** | 用 `web/vendor/plotly-cartesian-2.35.2.min.js`（1.3MB，只含 scatter/bar/heatmap 等笛卡尔图）。换图表类型前先确认该 bundle 支持，否则 `makePlot` 会静默画不出来 |
| **两个前端文件已无人引用** | `web/css/terminal.css`、`web/js/data-loader.js` 在架构归并后成为死文件，保留未删 |
| **`web/data/signals.json` 默认不存在** | 仓库不带 `data/latest_signals.csv`。signals.html 会显示"未生成"并给出 `python main.py signal` 两步命令，不会崩 |
| **百分比重复乘 100** | 见[数据契约](#前端数值口径)。IC 胜率 / 多空差曾因此显示 0~5000 |
| **`data/my_view.csv` 不入库** | 个人观点文件被 gitignore。缺失时程序自动生成模板 |
| **`web/data/daily.json` 含持仓与观点** | 仓库为 public，该文件含模拟持仓明细与 `my_view`。已确认可公开 |

### 已修复但值得记住的（2026-10-06 全面审查，50 项）

- 回测前视偏差（T-1 决策 → T 开盘成交）；涨跌停保护从"恒 False"到三级昨收回退
- 决策树方向反转：`max(0, score-1)` 曾把冰点日**升成 WARM**
- 前端 NaN 瘫痪：`SafeJSONEncoder` 对 float NaN 无效 → JSON 非法
- 深市指数 secid 硬编码：`399xxx` 永远拿不到；"涨停"实为涨幅排行
- 子串陷阱：`'不看好'.includes('看好')` 为真 → 观点判定反向
- 东财字段号错配：`clist` vs `stock/get`
- 首屏主图爆炸（2026-10-29）：涨停数与炸板率挤在双轴一张图里互相压制，2015 年极值又把
  其余 12 年压平。已拆成共享 X 轴的上下两栏，各加 5 日均线；区间按钮原写"3年"实为全样本，改为 全部/1年/3月
- 图表库单点故障（2026-10-29）：原先 5 个页面同步加载 `cdn.plot.ly`，CDN 一抽风
  `Plotly.react` 抛 ReferenceError 导致整页白屏。已改用本地 cartesian 包并保留缺库降级

更早的修复见 `git log`。

---

## 测试

```bash
python -m pytest tests/ -q
python -m unittest discover tests   # 无 pytest 时用 stdlib
```

CI（`.github/workflows/tests.yml`）：Ubuntu × Python 3.10 / 3.12 双版本，
push 与 PR 自动触发。CI 只装 pandas/numpy/pytest，akshare/baostock 缺失时
`tests/helpers.py` 自动注入 stub，不依赖网络。

**已知慢项**：`tests/test_daily_assistant.py` 的 3 个测试在有完整本地数据时
会跑很久（端到端 + 行业热度聚合），CI 上因无数据而 skip。本地全量跑约需 3 分钟以上，
建议开发时先 `--deselect` 这 3 项。

覆盖范围：回测时序契约（涨跌停 / 现金 / T+1 / 停牌估值 / 状态重置）、决策树降温方向、
仓位管理冷却与 sizing、市场状态守卫、因子除零与外围对齐、NaN 安全序列化、
`direct_data` 的 secid/涨跌停池解析、数据契约。

---

## 项目结构

```
ashare-regime-quant/
├── README.md                     # 本文件
├── ARCHITECTURE.md               # 架构决策与历史口径（改代码前先读）
├── STRATEGY_CONCLUSION.md        # 策略结论全文（负结果，必读）
├── A股交易守则.md                 # 四环境交易守则
├── PROSPECT_GAP.md
├── config.py                     # 全局配置（POOL/DATA/TRADE/REGIME/RISK/FACTOR/POLICY）
├── main.py                       # 唯一入口，17 个子命令
├── data/                         # 数据（daily/*.csv 不入库，约 98MB 可重下）
│   ├── my_view.csv.example       # 个人观点模板（真实文件 gitignore）
│   └── ...
├── src/
│   ├── data_loader.py            # 数据下载与缓存
│   ├── stock_pool.py             # 股票池过滤
│   ├── direct_data.py            # 东财裸 HTTP 实时数据
│   ├── daily_assistant.py        # 每日决策助手
│   ├── visualize.py              # Plotly HTML 报告
│   ├── serve_web.py              # Web 静态服务
│   ├── factors/                  # base / price_volume / sentiment / fundamental / money_flow / overseas
│   ├── sentiment/                # 情绪子系统（采集/聚合/决策树/埋伏检测/数据包生成）
│   ├── backtest/                 # engine / cross_cycle / experiment / rolling_pit / factor_analysis ...
│   ├── strategy/                 # multi_factor / guardian / user_view
│   └── utils/                    # market_regime / market_env / position_manager / industry_*
├── web/                          # 前端（无构建，直接开）
│   ├── js/shared.js              # ★ 唯一真源：导航/配色/图表基座/数据加载
│   ├── js/charts.js              # 情绪终端图表（依赖 shared.js）
│   ├── js/app.js                 # 情绪终端应用逻辑
│   ├── css/shared.css            # 全站样式（配色已过 WCAG AA）
│   ├── vendor/                   # 本地 Plotly cartesian 包（1.3MB，不依赖 CDN）
│   └── data/*.json               # 前端数据包
├── tests/                        # 21 个测试文件 / 121 个用例
└── notebooks/                    # 探索性分析
```

---

## 开发路线

**已完成**

- [x] 数据管线 / 股票池 / 因子框架 / 回测引擎 / 策略
- [x] 市场状态判断（慢牛专项 + 守则四环境）
- [x] 横截面 z-score + 分位数集中选股
- [x] 可视化报告（Plotly 交互式仪表盘）
- [x] walk-forward 分段滚动验证 / 12 年逐年滚动选池验证
- [x] 情绪周期子系统（3 年数据落库 + 决策树 + 埋伏检测）
- [x] Web 终端（8 页面 + 数据包生成器 + GitHub Pages 部署）
- [x] 单元测试套件 + CI（Python 3.10 / 3.12）
- [x] 2026-10-06 全面审查修复（回测时序契约重建）
- [x] 情绪择时假说检验（负结果已归档，防止重复踩坑）
- [x] 前端架构归并 + WCAG AA 配色（2026-10-15）
- [x] Plotly 本地化 + 首屏主图拆栏（2026-10-29，前端零外部依赖）

**待办**

- [ ] 改进因子与风控，使修复后口径下出现正期望
- [ ] 日线数据刷新后重跑段 3
- [ ] 涨停事件数据前复权口径全量重建
- [ ] 接入真实北向 / 港股 / 季度财务数据
- [ ] 因子 IC/IR 实盘验证

---

## 许可与免责

本项目仅供研究与学习。数据来自公开免费接口，**不构成投资建议**。
历史回测结果不代表未来收益。据此操作，风险自负。