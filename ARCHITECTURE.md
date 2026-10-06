# 架构与契约 (ARCHITECTURE.md)

> 单人项目的"伪团队"机制: 本文档写死层间文件契约, 由 CI 契约测试守护。
> 修改任何契约必须同步更新本文档与对应测试。
> 思维框架审查结论(2026-10-06)与本路线图见文末。

## 1. 数据流总览

```
baostock ──→ data/daily/*.csv ──┐
             data/index_*.csv ──┤
                                ├─→ src/strategy/multi_factor ──→ 回测 ──→ data/backtest_*.csv
akshare ──→ (外围/北向, 可降级) ─┘        │                                │
                                         └─→ data/latest_signals.csv      ├─→ gen_webdata ──→ web/data/*.json
                                                                          │         (NaN安全序列化)
baostock ──→ data/zt_events.csv ──→ src/sentiment/aggregate ──→ data/sentiment_3y.csv
             data/zhaban_events.csv        (按date,code去重)           │
                                                                       ├─→ gen_webdata
data/sentiment_3y.csv ──→ src/backtest/sentiment_timing (假说检验) ────┘
```

## 2. 文件契约(重点守护对象)

### data/daily/{code}.csv (Baostock 缓存, 不入库)
| 列 | 说明 |
|---|---|
| date, open, high, low, close | 前复权 K 线 |
| volume, amount, turnover | turnover 为百分数 |
| pctChg | 涨跌幅百分数(akshare 回退路径会自动补齐并统一 turnover 单位) |
| code | 6位字符串 |

### data/zt_events.csv (涨停事件, 追加写)
`date,code,lianban` — code 为6位; 消费方 aggregate 必须按 (date,code) 去重。
data/zhaban_events.csv: `date,code`。
data/zt_done.txt: 已完成整只历史的代码(全量重建口径); 增量模式改用 zt_state.csv。

### data/sentiment_3y.csv (情绪日线)
`date, zt_count, zhaban_count, zhaban_rate, lianban_height, lianban2, lianban3, lianban4p, shouban, shouban_ratio`

### data/backtest_equity.csv / backtest_trades.csv (回测输出)
equity: `date, equity, cash, positions, regime, position_pct`
trades: `date, code, action(BUY/SELL/SELL_FAIL), price, shares, cost_basis, signal, commission, pnl, pnl_pct, reason`

### web/data/*.json (前端数据包, 全部经 sanitize_json)
浏览器严格合法(无 NaN/Infinity 字面量)。新增文件需在 gen_webdata(_v2) 注册并在
web/js/data-loader.js 或页面脚本声明加载。

## 3. 回测时序契约(不可违反)

```
T-1 收盘数据 ──→ 因子/信号/状态/止损判断 ──→ T 开盘价±滑点成交 ──→ T 收盘仅盯市
```

- 因子必须是**后视纯**的: 第 t 行的值只能由 ≤t 的数据决定。
  全样本标准化/未来函数违反此契约 —— 等价性测试(test_factors 系)会失败。
- 涨跌停: 昨收三级回退(pre_close 列 → pctChg 反推 → 前一根收盘);
  主板 10%, 创业板(300/301)/科创板(688) 20%; 开盘封死双向禁成交。
- 停牌: 按最近有效收盘估值, 不归零。
- T+1: 买入当日不可卖出。

## 4. 模块状态(2026-10-06 剃刀审查)

| 模块 | 状态 | 说明 |
|---|---|---|
| src/data_loader.py | **活跃** | 双源+指数缓存+降级链 |
| src/strategy/multi_factor.py | **活跃** | 主回测路径; 因子面板已向量化 |
| src/backtest/engine.py | **活跃** | 时序契约见上 |
| src/backtest/sentiment_timing.py | **活跃(研究)** | 冰点择时假说已证伪, 负结果归档 |
| src/sentiment/*(管线) | **活跃** | 事件抓取→聚合; 增量模式见下 |
| src/sentiment/decision_tree.py | 冻结 | 未接入生产回路; 保留作策略参考 |
| src/backtest/swing_backtest.py | 冻结 | 第二套引擎, 无正期望证据; 保留不维护 |
| src/visualize.py (HTML报告) | 半冻结 | 与 web 终端功能重叠; 不新增功能 |
| src/factors/overseas.py | 半冻结 | 美股因子可用; 港股/北向为占位, 权重表已剔除 |

## 5. 路线图(九框架审查后的优先级)

1. ~~情绪择时假说检验~~ ✅ 已证伪(负结果归档 README)
2. ~~因子面板向量化~~ ✅ 等价性证明(test_factor_panel)+ 回测 15分钟→26秒
3. ~~情绪管线增量化~~ ✅ worker 状态文件(断点=最后抓取日+连板计数)/scheduler --update
4. [进行中] 前复权口径全量重建(约2小时, 旧口径事件已归档 _archive/unadjusted_events_20261006)
5. 数据 manifest + 契约冒烟测试(CI 守护 schema 漂移)
6. 改进因子与风控, 使修复后口径出现正期望(核心目标)

### 情绪数据日常更新(增量化后)
```bash
python -m src.sentiment.rebuild_scheduler --update   # 仅抓落后于最近交易日的代码
python -m src.sentiment.aggregate_sentiment          # 聚合(自动去重)
python main.py gen-webdata                           # 刷新前端数据包
```

## 6. 已知负结果(防止重复踩坑)

- 多因子体系(19因子z-score加权): 修复后口径 -2.15%, 0/3段正收益 → 需重做
- 冰点择时(指数层面): 全变体跑输买入持有, 3日变体利润=单笔924行情 → 证伪
- "连续冰点=更强洗盘": 胜率反降至18-31% → 证伪
- **成本归因(2026-10-06, 前300只诊断)**: 现行费用-5.64% vs 零费用-5.20%,
  成本仅贡献0.44pp → 负期望来自信号本身, 降频/省成本不是出路; 且期间风控层
  多次"熔断→冷却→再入→再熔断"锯齿, 风控参数与信号质量需一起审视
- **权重景观(2026-10-06, 前300只×3段)**: BULL动量权重{0,0.5,1,1.5}四点全部
  段均负收益(-3.9%~-8.8%), 邻域无正期望区; 基准与1.5倍几乎相同 → 样本期
  BULL状态极少, 动量维度根本未被充分测试。结论: 微调权重救不了, 需要换信号
- 详见 README"关键修复记录"与 git log
