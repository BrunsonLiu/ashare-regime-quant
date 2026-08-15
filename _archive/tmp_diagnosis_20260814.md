# 数据链路诊断（2026-08-14 21:15）

## 用户问：现在还有啥不行的

## 诊断结果（按严重度）

### ① 日线数据断更 2 周（最致命）
- data/daily/ 4400 只：4225 只停在 07-31，仅 183 只到 08-12，08-13/14 几乎无
- 原因：8-2 全量下载后未跑 `python main.py data` 增量更新
- 影响：因子/回测/信号全吃过期 2 周数据

### ② 情绪数据滞后 1 天
- zt_events/zhaban_events/sentiment_3y 全停在 08-13
- 08-14（周五）是交易日（上证 3927.18），当日数据缺失

### ③ 股票池与 config 脱节
- config.py 8-4 改 board_filter=["60","00"]（只主板）
- stock_pool.csv 仍为 8-2 旧池 4400 只（含创业板 1398 + 北交 975）
- 情绪重建/日线下载基于脏池

### ④ 涨停阈值 bug
- rebuild_worker.get_limit_pct 只分 10cm(0.098)/20cm(0.198)
- 北交所 30cm(0.298) 未处理 → 12967 条北交涨停记录失真

## 修复顺序建议
1. 补情绪到 08-14（增量 rebuild_worker / scheduler 续传）
2. python main.py data（补 4400 只日线）
3. python main.py pool（重建股票池，board_filter 生效）
4. 修 get_limit_pct 加北交 0.298 分支后重跑情绪重建

## 关键事实核对
- baostock 直连正常，08-14 上证指数/个股数据可取
- zt_events.csv 前导零在 pandas 读取时被丢（int64），文件本身存的是补零字符串，非数据错误
- stock_pool.csv 生成时间 8-2 15:38，config.py 修改 8-4 1:11 → 池未随 config 重建
