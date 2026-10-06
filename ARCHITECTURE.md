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

## 6. 已知负结果 与 更正后的结论(防止重复踩坑)

> ⚠️ 2026-10-06 更正: 早期"信号本身是负的"结论**错误**——它比较的是绝对收益,
> 没有减掉市场 beta。样本期是**小盘股熊市**(universe 等权 B&H 均值 -13.73%,
> 中位 -16.95%, 仅18%个股上涨), 必须看超额收益。以下为带基准的更正结论。

- **策略确有正超额(样本内)**: 现行费用 -9.58% vs 基准 -13.73% = **+4.15pp**;
  零费用 +5.92pp。绝对亏损主要是市场 beta, 不是策略失效。
- **成本真实贡献约1.8pp**(现行 vs 零费用), 值得关注但不是主要矛盾。
- **单因子归因(13因子, 正超额6个)**: 熊市均值回归画像——
  * 强: volatility_20(-)偏好高波动 +6.33pp, momentum_20(-)20日反转 +5.87pp,
    ma_align均线多头 +3.99pp
  * 弱/有害: 追涨停 -3.56pp, 追涨动量 -1.87pp, turnover_avg -8.24pp,
    price_gap -7.64pp
  * 现有19因子混合(+5.92pp)并未明显超过最佳单因子(+6.33pp) → 因子冗余,
    有害因子在拖后腿
- **熔断永久锁死bug(已修)**: peak_equity只涨不跌导致深度回撤后每10日精确
  再熔断, 旧基线含3.5个月空仓被意外美化; 修复后基线-9.58%才无偏
- **冰点择时(指数层面)**: 全变体跑输买入持有 → 证伪(此结论有基准对照, 成立)
- **"连续冰点=更强洗盘"**: 胜率反降至18-31% → 证伪

### 重要警示
上述正超额均为**单样本(2025-11~2026-09单一行情段)、前300只、样本内**结果,
且13因子多重比较下最佳因子的+6.33pp可能是运气。**下一步必须做样本外验证**
(不同行情段/不同universe), 否则不能作为策略有效性的证据。
