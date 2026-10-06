"""
A股量化系统 - 主程序入口
毛选思想驱动的量化交易系统

用法:
    python main.py pool         # 构建股票池
    python main.py data         # 下载日线数据
    python main.py regime      # 查看市场状态（MA判断）
    python main.py live         # 实时概览（涨停/板块/指数）
    python main.py signal       # 生成交易信号
    python main.py backtest     # 运行回测
    python main.py factors      # 因子有效性分析
    python main.py principles   # 打印毛选原则映射
    python main.py overseas     # 查看外围市场
    python main.py report       # 生成可视化报告(HTML仪表盘)
    python main.py walkforward  # walk-forward 滚动验证(分段稳定性)
    python main.py gen-webdata  # 生成全量前端数据包(JSON, 含6大模块)
    python main.py serve-web    # 启动Web前端服务(localhost:8899)
    python main.py dashboard    # 生成数据包 + 启动Web服务
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATA_DIR


def build_pool():
    """构建股票池"""
    from src.stock_pool import StockPool
    sp = StockPool()
    pool = sp.build()
    if pool is None or len(pool) == 0:
        print("股票池构建失败（数据源不可用或非交易日），请稍后重试")
        return
    sp.save(pool)

    if 'amount' in pool.columns:
        top20 = pool.nlargest(20, 'amount')
        print("\n成交额前20：")
        print(top20[['code', 'name', 'amount', 'turnover']].to_string(index=False))


def download_data():
    """下载股票池中所有股票的日线数据"""
    from src.stock_pool import StockPool
    from src.data_loader import DataLoader

    sp = StockPool()
    pool = sp.load()
    if pool is None:
        print("请先构建股票池: python main.py pool")
        return

    codes = pool['code'].tolist()
    print(f"准备下载 {len(codes)} 只股票的日线数据...")

    loader = DataLoader()
    data = loader.get_daily_batch(codes, days=250)
    print(f"成功下载 {len(data)} 只")


def show_regime():
    """查看当前市场状态"""
    from src.data_loader import DataLoader
    from src.utils.market_regime import MarketRegime

    loader = DataLoader()
    index_df = loader.get_index_data("000001", days=300)

    if index_df is None or len(index_df) == 0:
        print("指数数据获取失败，请稍后重试")
        return

    regime = MarketRegime()
    state = regime.detect(index_df)

    print("\n" + "="*50)
    print("市场状态分析")
    print("="*50)
    for k, v in state.items():
        if isinstance(v, dict):
            print(f"\n  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")

    regime_name = state.get('regime', 'UNKNOWN')
    print("\n" + "="*50)
    if regime_name == 'BULL':
        print("[BULL] 牛市 -> 重仓出击，主线持仓不动")
    elif regime_name == 'BEAR':
        print("[BEAR] 空头 -> 保存实力，轻仓超跌反弹")
    else:
        print("[SHOCK] 震荡 -> 轻仓短线，逆向为主")
    print("="*50)


def generate_signal():
    """生成交易信号"""
    from src.stock_pool import StockPool
    from src.data_loader import DataLoader
    from src.strategy.multi_factor import MultiFactorStrategy

    sp = StockPool()
    pool = sp.load()
    if pool is None:
        print("请先构建股票池: python main.py pool")
        return

    loader = DataLoader()
    index_df = loader.get_index_data("000001", days=300)

    if index_df is None or len(index_df) == 0:
        print("指数数据获取失败")
        return

    # 加载数据（先用缓存）
    codes = pool['code'].tolist()[:300]  # 先用前300只
    data_dict = {}
    for code in codes:
        df = loader.load_cache(code)
        if df is not None:
            data_dict[code] = df

    if len(data_dict) == 0:
        print("无缓存数据，请先运行: python main.py data")
        return

    print(f"加载了 {len(data_dict)} 只股票数据")
    if len(data_dict) < 5:
        print("警告：股票数据不足，请先运行 python main.py data")
        return

    strategy = MultiFactorStrategy()
    signals = strategy.generate_signals(data_dict, index_df, pool)

    if len(signals) > 0:
        signals.to_csv(
            os.path.join(DATA_DIR, 'latest_signals.csv'),
            index=False, encoding='utf-8-sig'
        )
        print(f"\n信号已保存到 data/latest_signals.csv")
        print(f"买入信号: {len(signals[signals['signal']>0])} 只")
        print(f"卖出信号: {len(signals[signals['signal']<0])} 只")


def run_backtest():
    """运行回测"""
    from src.stock_pool import StockPool
    from src.data_loader import DataLoader
    from src.strategy.multi_factor import MultiFactorStrategy
    from src.backtest.engine import BacktestEngine

    sp = StockPool()
    pool = sp.load()
    if pool is None:
        print("请先构建股票池")
        return

    loader = DataLoader()
    index_df = loader.get_index_data("000001", days=400)

    if index_df is None or len(index_df) == 0:
        print("指数数据获取失败，无法回测")
        return

    # 加载数据（小批量避免内存爆炸）
    # code统一为字符串（避免与data_dict字符串key不匹配）
    pool['code'] = pool['code'].astype(str).str.zfill(6)
    # 过滤创业板(30xxx)和科创板(68xxx)
    pool = pool[~pool['code'].str.startswith('30') & ~pool['code'].str.startswith('68')]
    # 按流动性(成交额)降序取 top N：流动性优先 + 控内存（避免全量OOM）
    if 'amount' in pool.columns:
        pool = pool.sort_values('amount', ascending=False)
    top_n = 800
    codes = pool['code'].head(top_n).tolist()
    print(f"回测范围: 主板流动性前 {len(codes)} 只")
    data_dict = {}
    for code in codes:
        df = loader.load_cache(code)
        if df is not None:
            data_dict[code] = df

    print(f"加载了 {len(data_dict)} 只股票数据")
    # 打印数据时间范围
    if data_dict:
        first_code = list(data_dict.keys())[0]
        dates = data_dict[first_code]['date'].tolist()
        print(f"数据范围: {dates[0]} ~ {dates[-1]}，共{len(dates)}个交易日")
    if len(data_dict) < 5:
        print("警告：股票数据不足，请先运行 python main.py data")
        return

    strategy = MultiFactorStrategy()
    result = strategy.backtest_with_regime(data_dict, index_df, pool)

    if result is None:
        print("回测失败")
        return

    print("\n" + "="*50)
    print("回测结果")
    print("="*50)
    for k, v in result['stats'].items():
        print(f"  {k}: {v}")

    # 保存结果（用绝对路径）
    base = os.path.dirname(os.path.abspath(__file__))
    eq_path = os.path.join(base, 'data', 'backtest_equity.csv')
    result['equity_curve'].to_csv(eq_path, index=False, encoding='utf-8-sig')
    if len(result['trades']) > 0:
        result['trades'].to_csv(
            os.path.join(base, 'data', 'backtest_trades.csv'),
            index=False, encoding='utf-8-sig'
        )
    print("\n回测结果已保存到 data/\n[BACKTEST_DONE]")


def run_walkforward(n_segments=3, warmup=120, top_n=800):
    """walk-forward 滚动验证：把回测期切为若干连续测试窗口，逐段回测，
    验证策略在不同行情段是否稳定盈利（而非依赖单一牛市段导致过拟合假象）"""
    import numpy as np
    import pandas as pd
    from src.stock_pool import StockPool
    from src.data_loader import DataLoader
    from src.strategy.multi_factor import MultiFactorStrategy

    sp = StockPool()
    pool = sp.load()
    if pool is None:
        print("请先构建股票池")
        return

    loader = DataLoader()
    index_df = loader.get_index_data("000001", days=400)

    if index_df is None or len(index_df) == 0:
        print("指数数据获取失败，无法 walk-forward")
        return

    pool['code'] = pool['code'].astype(str).str.zfill(6)
    pool = pool[~pool['code'].str.startswith('30') & ~pool['code'].str.startswith('68')]
    if 'amount' in pool.columns:
        pool = pool.sort_values('amount', ascending=False)
    codes = pool['code'].head(top_n).tolist()
    data_dict = {}
    for code in codes:
        df = loader.load_cache(code)
        if df is not None:
            data_dict[code] = df
    if len(data_dict) < 5:
        print("警告：股票数据不足，请先运行 python main.py data")
        return
    print(f"walk-forward: {len(data_dict)} 只, 切 {n_segments} 段 (预热 {warmup} 交易日)")

    # 基于股票数据确定有效测试窗口（rolling(120) 等因子需足够历史，避免前期因子全 NaN 污染结论）
    sample_code = list(data_dict.keys())[0]
    stock_dates = sorted(data_dict[sample_code]['date'].astype(str).unique())
    if len(stock_dates) <= warmup:
        print("股票数据不足，无法 walk-forward")
        return
    stock_trade_start = stock_dates[warmup]
    all_dates = sorted(index_df['date'].astype(str).unique())
    trade_dates = [d for d in all_dates if d >= stock_trade_start]
    if len(trade_dates) < n_segments:
        n_segments = max(1, len(trade_dates) // 10)
    seg_bounds = np.array_split(trade_dates, n_segments)

    strategy = MultiFactorStrategy()
    seg_results = []
    for k, seg in enumerate(seg_bounds):
        s, e = str(seg[0]), str(seg[-1])
        print(f"\n=== 段 {k+1}/{n_segments}: {s} ~ {e} ===", flush=True)
        result = strategy.backtest_with_regime(data_dict, index_df, pool, start_date=s, end_date=e)
        if result is None:
            print("  段失败", flush=True)
            continue
        eq = result['equity_curve']
        eq['date'] = eq['date'].astype(str)
        eq_seg = eq[(eq['date'] >= s) & (eq['date'] <= e)]
        if len(eq_seg) < 2:
            print("  段数据不足", flush=True)
            continue
        start_eq = eq_seg['equity'].iloc[0]
        end_eq = eq_seg['equity'].iloc[-1]
        seg_ret = (end_eq / start_eq - 1) * 100
        peak = eq_seg['equity'].expanding().max()
        dd = ((eq_seg['equity'] - peak) / peak).min() * 100
        dret = eq_seg['equity'].pct_change().dropna()
        sharpe = dret.mean() / (dret.std() + 1e-8) * np.sqrt(252) if len(dret) > 1 else 0.0
        tr = result.get('trades')
        if tr is not None and len(tr) > 0:
            sells = tr[tr['action'] == 'SELL']
            win_rate = (sells['pnl'] > 0).sum() / len(sells) * 100 if len(sells) > 0 else 0.0
            n_tr = len(tr)
        else:
            win_rate, n_tr = 0.0, 0
        seg_results.append({
            'seg': k + 1, 'start': s, 'end': e,
            'ret_pct': round(float(seg_ret), 2),
            'max_dd_pct': round(float(dd), 2),
            'sharpe': round(float(sharpe), 2),
            'win_rate': round(float(win_rate), 1),
            'n_trades': int(n_tr),
        })
        print(f"  收益 {seg_ret:+.2f}%  回撤 {dd:.2f}%  夏普 {sharpe:.2f}  胜率 {win_rate:.1f}%  交易 {n_tr}", flush=True)

    if not seg_results:
        print("无有效段")
        return

    print("\n" + "=" * 50)
    print("Walk-Forward 汇总")
    print("=" * 50)
    rets = [r['ret_pct'] for r in seg_results]
    pos = sum(1 for x in rets if x > 0)
    print(f"段数: {len(seg_results)}  正收益段: {pos}/{len(seg_results)} ({pos / len(seg_results) * 100:.0f}%)")
    print(f"平均段收益: {np.mean(rets):+.2f}%  最小: {min(rets):+.2f}%  最大: {max(rets):+.2f}%")
    verdict = "稳定（多段正收益，不依赖单一行情）" if pos / len(seg_results) >= 0.6 else "不稳定（依赖特定行情段，过拟合风险高）"
    print(f"结论: {verdict}")
    base = os.path.dirname(os.path.abspath(__file__))
    pd.DataFrame(seg_results).to_csv(os.path.join(base, 'data', 'walkforward.csv'), index=False, encoding='utf-8-sig')
    print("\n已保存到 data/walkforward.csv")


def analyze_factors():
    """因子有效性分析"""
    from src.stock_pool import StockPool
    from src.data_loader import DataLoader
    from src.backtest.factor_analysis import FactorAnalysis

    sp = StockPool()
    pool = sp.load()
    if pool is None:
        print("请先构建股票池")
        return

    loader = DataLoader()
    codes = pool['code'].tolist()[:100]
    data_dict = {}
    for code in codes:
        df = loader.load_cache(code)
        if df is not None:
            data_dict[code] = df

    print(f"加载了 {len(data_dict)} 只股票数据")
    print("\n因子分析需要足够的日线数据，请确保已下载数据")

    # 示例：分析动量因子
    fa = FactorAnalysis()

    from src.factors.price_volume import Momentum
    mom = Momentum(20)

    factor_records = []
    return_records = []

    for code, df in data_dict.items():
        if len(df) < 60:
            continue
        f = mom.calculate(df)
        for i in range(len(df)):
            factor_records.append({
                'date': df.iloc[i]['date'],
                'code': code,
                'factor_value': f.iloc[i] if not np.isnan(f.iloc[i]) else None,
            })
            return_records.append({
                'date': df.iloc[i]['date'],
                'code': code,
                'close': df.iloc[i]['close'],
            })

    if len(factor_records) < 100:
        print("数据不足，请下载更多数据")
        return

    factor_df = pd.DataFrame(factor_records)
    return_df = pd.DataFrame(return_records)

    print("\n分析动量因子...")
    ic_df = fa.calc_ic_series(factor_df, return_df)
    summary = fa.ic_summary(ic_df)
    print(summary.to_string(index=False))


def show_principles():
    """打印毛选原则映射"""
    from src.utils.mao_principles import print_principles
    print_principles()


def show_live():
    """实时市场概览（涨停/板块/指数）"""
    from src.direct_data import get_fetcher
    fetcher = get_fetcher()
    print("="*50)
    print("实时市场概览")
    print("="*50)

    # 涨停统计
    try:
        lu = fetcher.get_limit_up(limit=200)
        ld = fetcher.get_limit_down(limit=100)
        print(f"\n【涨跌停】 涨停: {len(lu)}  跌停: {len(ld)}")
        if len(lu) > 0:
            print("\n【涨停股TOP10】")
            for _, r in lu.head(10).iterrows():
                amt = r.get('amount', 0) or 0
                chg = r.get('chg_pct') or 0
                print(f"  {r['name']:<10} {chg:+.2f}%  成交:{amt/1e8:>5.1f}亿")
    except Exception as e:
        print(f"涨停数据获取失败: {e}")

    # 板块排行
    try:
        sec = fetcher.get_sector_ranking(top_n=10)
        if len(sec) > 0:
            print("\n【板块涨幅排行TOP10】")
            for _, s in sec.iterrows():
                chg = s.get('涨跌幅', 0) or 0
                print(f"  {s['板块名称']:<12} {chg:+.2f}%")
    except Exception as e:
        print(f"板块数据获取失败: {e}")

    # 指数
    try:
        idx = fetcher.get_index_realtime(['000001', '399001', '399006', '000300'])
        if len(idx) > 0:
            print("\n【主要指数】")
            for _, r in idx.iterrows():
                chg = r.get('chg_pct', 0) or 0
                arrow = "+" if chg >= 0 else ""
                print(f"  {r['name']:<10} {str(r.get('close','')):>10}  {arrow}{chg:.2f}%")
    except Exception as e:
        print(f"指数数据获取失败: {e}")

    print("="*50)


def show_overseas():
    """查看外围市场（支持双数据源格式）"""
    from src.data_loader import DataLoader
    loader = DataLoader()
    overview = loader.get_global_overview()

    print("\n" + "="*50)
    print("外围市场概览")
    print("="*50)

    if not overview:
        print("数据获取失败，可能是网络问题或非交易时段")
        return

    has_chg = False
    for name, info in overview.items():
        chg = info.get('chg_pct')
        close = info.get('close')
        date = info.get('date', '')
        note = info.get('note', '')
        if chg is not None:
            has_chg = True
            arrow = "🔴 +" if chg > 0 else "🟢 " if chg < 0 else "⚪ "
            print(f"  {name}: {close} ({arrow}{chg:+.2f}%) [{date}]")
        elif note:
            print(f"  {name}: {note}  [{date}]")
        else:
            val = info.get('value', info.get('net_flow', ''))
            print(f"  {name}: {val}  [{date}]")

    us_chg = overview.get('标普500', {}).get('chg_pct') or 0
    hk_chg = overview.get('恒生指数', {}).get('chg_pct') or 0
    total = (us_chg + hk_chg) / 2

    print(f"\n  综合影响: {total:+.2f}%")
    if total > 0.5:
        print("  判断: 外围偏强 → A股次日可能高开")
    elif total < -0.5:
        print("  判断: 外围偏弱 → A股次日可能低开，注意风险")
    else:
        print("  判断: 外围中性 → A股走自身逻辑")


def generate_report():
    """生成可视化报告（HTML仪表盘）"""
    from src.visualize import generate_report as _gen
    _gen()

def gen_webdata():
    """生成前端可视化数据包（全量模块）"""
    from src.sentiment.gen_webdata_v2 import main as _gen
    _gen()

def serve_web():
    """启动Web前端服务"""
    from src.serve_web import main as _serve
    _serve()

def dashboard():
    """生成数据包 + 启动Web服务"""
    gen_webdata()
    print()
    serve_web()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    commands = {
        "pool": build_pool,
        "data": download_data,
        "regime": show_regime,
        "live": show_live,
        "signal": generate_signal,
        "backtest": run_backtest,
        "factors": analyze_factors,
        "principles": show_principles,
        "overseas": show_overseas,
        "report": generate_report,
        "walkforward": run_walkforward,
        "gen-webdata": gen_webdata,
        "serve-web": serve_web,
        "dashboard": dashboard,
    }

    if cmd == "help":
        print(__doc__)
    elif cmd in commands:
        commands[cmd]()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
