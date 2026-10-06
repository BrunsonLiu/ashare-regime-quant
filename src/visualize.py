# -*- coding: utf-8 -*-
"""
A股量化策略 · 专业可视化仪表盘 v2
风格：深色金融终端（Bloomberg Terminal inspired）
功能：净值曲线 / 回撤 / 市场状态 / 月度热力图 / Walk-Forward / 
      完整交易流水表(可排序/搜索/同花顺跳转) / 个股K线+买卖点标注 / 
      技术指标叠加 / 因子权重 / 战法分类统计
"""
import os
import json
import datetime as dt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from config import DATA_DIR, RESULT_DIR, TRADE_CONFIG

# ========== 全局路由 ==========
THS_URL = "https://stockpage.10jqka.com.cn/{code}/"          # 同花顺个股
# 东方财富个股页前缀按市场选择: 6开头沪市sh, 其余深市sz
EASTMONEY_URL = "https://quote.eastmoney.com/concept/{mkt}{code}.html"

THEME = {
    'bg': '#0d1117',
    'card': '#161b22',
    'border': '#21262d',
    'text': '#e6edf3',
    'muted': '#9da7b3',
    'accent': '#4fd1c5',
    'green': '#48bb78',
    'red': '#f56565',
    'yellow': '#f6ad55',
    'blue': '#63b3ed',
    'purple': '#b794f4',
}

CMAP_REGIME = {'BULL': THEME['green'], 'SHOCK': THEME['yellow'], 'BEAR': THEME['red'], 'UNKNOWN': THEME['muted']}


def _style(fig, title, height=380):
    fig.update_layout(
        title=dict(text=title, font=dict(color=THEME['text'], size=14), x=0.01, xanchor='left'),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=THEME['muted'], family='-apple-system,Segoe UI,Roboto,Helvetica,Arial,"Microsoft YaHei",sans-serif'),
        margin=dict(l=55, r=22, t=50, b=40),
        height=height,
        xaxis=dict(gridcolor='rgba(255,255,255,0.06)', zerolinecolor='rgba(255,255,255,0.1)', linecolor='rgba(255,255,255,0.12)', rangeselector=None),
        yaxis=dict(gridcolor='rgba(255,255,255,0.06)', zerolinecolor='rgba(255,255,255,0.1)', linecolor='rgba(255,255,255,0.12)'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0, font=dict(size=11)),
        hovermode='x unified',
    )
    return fig


# ========== 数据加载 ==========

def _load_stock_pool():
    """加载股票池 → {code: name}"""
    pool_path = os.path.join(DATA_DIR, 'stock_pool.csv')
    if not os.path.exists(pool_path):
        return {}
    pool = pd.read_csv(pool_path, encoding='utf-8-sig')
    pool['code'] = pool['code'].astype(int).astype(str).str.zfill(6)
    return dict(zip(pool['code'], pool['name']))


def _load_equity():
    eq_path = os.path.join(DATA_DIR, 'backtest_equity.csv')
    if not os.path.exists(eq_path):
        return None
    eq = pd.read_csv(eq_path)
    eq['date'] = eq['date'].astype(str)
    return eq


def _load_trades():
    tr_path = os.path.join(DATA_DIR, 'backtest_trades.csv')
    if not os.path.exists(tr_path):
        return pd.DataFrame()
    t = pd.read_csv(tr_path, dtype={'code': str})
    t['code'] = t['code'].str.zfill(6)
    return t


def _load_walkforward():
    wf_path = os.path.join(DATA_DIR, 'walkforward.csv')
    if not os.path.exists(wf_path):
        return None
    return pd.read_csv(wf_path)


# ========== 统计 ==========

def _calc_stats(equity_df, trades_df):
    stats = {}
    if equity_df is None or len(equity_df) == 0:
        return stats
    eq = equity_df['equity'].astype(float)
    init = float(TRADE_CONFIG.get('initial_capital', eq.iloc[0]))
    end = eq.iloc[-1]
    stats['总收益率'] = (end / init - 1) * 100
    peak = eq.expanding().max()
    dd = (eq - peak) / peak
    stats['最大回撤'] = dd.min() * 100
    daily = eq.pct_change().dropna()
    stats['夏普比率'] = daily.mean() / (daily.std() + 1e-8) * np.sqrt(252)
    stats['期末资金'] = end
    stats['总交易日'] = len(eq)
    stats['年化收益'] = ((end / init) ** (252 / max(len(eq), 1)) - 1) * 100
    stats['卡玛比率'] = stats['年化收益'] / max(abs(stats['最大回撤']), 1e-8)
    # 最大连续盈利天数/亏损天数
    dd_mask = dd < -0.001
    max_dd_dur = 0
    cur = 0
    for v in dd_mask:
        if v:
            cur += 1
            max_dd_dur = max(max_dd_dur, cur)
        else:
            cur = 0
    stats['最大回撤持续'] = max_dd_dur

    if trades_df is not None and len(trades_df) > 0:
        sells = trades_df[trades_df['action'] == 'SELL']
        n = len(sells)
        if n > 0:
            wins = int((sells['pnl'] > 0).sum())
            stats['总交易次数'] = n
            stats['胜率'] = (wins / n * 100) if n > 0 else 0.0
            avg_win = sells.loc[sells['pnl'] > 0, 'pnl'].mean() if wins > 0 else 0.0
            avg_loss = sells.loc[sells['pnl'] <= 0, 'pnl'].mean() if (n - wins) > 0 else 0.0
            stats['平均盈利'] = avg_win
            stats['平均亏损'] = avg_loss
            stats['盈亏比'] = (abs(avg_win / avg_loss) if avg_loss != 0 else float('nan'))
            stats['最大单笔盈利'] = sells['pnl'].max()
            stats['最大单笔亏损'] = sells['pnl'].min()
            # 平均持仓天数
            stats['平均盈利次数'] = wins
            stats['平均亏损次数'] = n - wins
    return stats


def _get_benchmark(equity_df):
    try:
        from src.data_loader import DataLoader
        loader = DataLoader()
        idx = loader.get_index_data("000001", days=400)
        if idx is None or len(idx) == 0:
            return None
        idx = idx.copy()
        idx['date'] = idx['date'].astype(str)
        eq_dates = set(equity_df['date'].astype(str))
        idx = idx[idx['date'].isin(eq_dates)]
        if len(idx) < 5:
            return None
        first_eq = equity_df['date'].astype(str).iloc[0]
        if first_eq in set(idx['date']):
            base = idx.loc[idx['date'] == first_eq, 'close'].iloc[0]
        else:
            base = idx['close'].iloc[0]
        init_cap = float(TRADE_CONFIG.get('initial_capital', equity_df['equity'].iloc[0]))
        idx = idx.sort_values('date')
        out = pd.DataFrame({'date': idx['date'].values, 'equity': (idx['close'].values / base * init_cap)})
        return out
    except Exception as e:
        print(f"  [!] 基准获取失败: {e}")
        return None


# ========== 图表：净值曲线 ==========

def _fig_equity(equity_df, idx_norm, trades_df=None):
    fig = go.Figure()
    # 策略净值
    fig.add_trace(go.Scatter(
        x=equity_df['date'], y=equity_df['equity'], mode='lines', name='策略净值',
        line=dict(color=THEME['accent'], width=2.5),
        fill='tozeroy', fillcolor='rgba(79,209,197,0.08)',
        hovertemplate='%{x}<br>净值: %{y:,.0f}<extra>策略</extra>',
    ))
    # 上证基准
    if idx_norm is not None and len(idx_norm) > 0:
        fig.add_trace(go.Scatter(
            x=idx_norm['date'], y=idx_norm['equity'], mode='lines', name='上证指数(基准)',
            line=dict(color=THEME['yellow'], width=1.2, dash='dot'),
            hovertemplate='%{x}<br>基准: %{y:,.0f}<extra>上证指数</extra>',
        ))
    # 交易点标记
    if trades_df is not None and len(trades_df) > 0:
        buys = trades_df[trades_df['action'] == 'BUY']
        sells = trades_df[trades_df['action'] == 'SELL']
        if 'pnl' in trades_df.columns:
            win_sells = sells[sells['pnl'] > 0]
            lose_sells = sells[sells['pnl'] <= 0]
        else:
            win_sells, lose_sells = sells, pd.DataFrame()
        # 标注买入日净值
        buy_dates_set = set(buys['date'])
        eq_buy = equity_df[equity_df['date'].isin(buy_dates_set)]
        if len(eq_buy) > 0:
            fig.add_trace(go.Scatter(
                x=eq_buy['date'], y=eq_buy['equity'], mode='markers', name='买入',
                marker=dict(color=THEME['green'], size=7, symbol='triangle-up', line=dict(width=1, color=THEME['bg'])),
                hovertemplate='买入日<extra></extra>',
            ))
        win_dates = set(win_sells['date']) if len(win_sells) > 0 else set()
        lose_dates = set(lose_sells['date']) if len(lose_sells) > 0 else set()
        eq_win = equity_df[equity_df['date'].isin(win_dates)]
        eq_lose = equity_df[equity_df['date'].isin(lose_dates)]
        if len(eq_win) > 0:
            fig.add_trace(go.Scatter(
                x=eq_win['date'], y=eq_win['equity'], mode='markers', name='盈利卖出',
                marker=dict(color=THEME['green'], size=7, symbol='triangle-down', line=dict(width=1, color=THEME['bg'])),
                hovertemplate='盈利卖<extra></extra>',
            ))
        if len(eq_lose) > 0:
            fig.add_trace(go.Scatter(
                x=eq_lose['date'], y=eq_lose['equity'], mode='markers', name='亏损卖出',
                marker=dict(color=THEME['red'], size=7, symbol='triangle-down', line=dict(width=1, color=THEME['bg'])),
                hovertemplate='亏损卖<extra></extra>',
            ))
    return _style(fig, "策略净值 vs 上证指数 (▲买入  ▼卖出)", height=440)


# ========== 图表：回撤 ==========

def _fig_drawdown(equity_df):
    eq = equity_df['equity'].astype(float)
    peak = eq.expanding().max()
    dd = (eq - peak) / peak * 100
    # 回撤填充色：根据回撤深度
    colors = ['rgba(245,101,101,0.25)' if v < -8 else 'rgba(245,101,101,0.10)' if v < -4 else 'rgba(245,101,101,0.04)' for v in dd]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df['date'], y=dd, mode='lines', name='回撤%',
        line=dict(color=THEME['red'], width=1.6),
        fill='tozeroy', fillcolor='rgba(245,101,101,0.08)',
        hovertemplate='%{x}<br>回撤: %{y:.2f}%<extra></extra>',
    ))
    # 标注熔断线 -8%
    fig.add_hline(y=-8, line_dash='dash', line_color='rgba(245,101,101,0.6)', opacity=0.7,
                  annotation_text='熔断线 -8%', annotation_position='bottom right', annotation_font_color=THEME['red'])
    return _style(fig, "回撤曲线", height=280)


# ========== 图表：市场状态时间线 ==========

def _fig_regime(equity_df):
    regs = equity_df['regime'].astype(str).tolist()
    colors = [CMAP_REGIME.get(r, THEME['muted']) for r in regs]
    fig = go.Figure()
    # 用背景带色块表示状态
    regimes_unique = []
    cur_regime = regs[0]
    start_idx = 0
    for i, r in enumerate(regs):
        if r != cur_regime:
            regimes_unique.append((start_idx, i - 1, cur_regime))
            cur_regime = r
            start_idx = i
    regimes_unique.append((start_idx, len(regs) - 1, cur_regime))

    for si, ei, rn in regimes_unique:
        fig.add_vrect(
            x0=equity_df['date'].iloc[si], x1=equity_df['date'].iloc[ei],
            fillcolor=CMAP_REGIME.get(rn, THEME['muted']),
            opacity=0.18, line_width=0, layer='below',
            annotation_text=rn, annotation_position='top left',
            annotation_font=dict(color=CMAP_REGIME.get(rn, THEME['muted']), size=10)
        )
    # 加一条净值线
    fig.add_trace(go.Scatter(
        x=equity_df['date'], y=equity_df['equity'], mode='lines', name='净值',
        line=dict(color=THEME['accent'], width=2.5),
    ))
    vc = pd.Series(regs).value_counts()
    ann = " | ".join([f"{k}:{v/len(regs)*100:.0f}%" for k, v in vc.items()])
    fig.update_layout(margin=dict(l=55, r=22, t=50, b=20))
    fig.add_annotation(text=ann, xref='paper', yref='paper', x=0.5, y=1.08, showarrow=False, font=dict(color=THEME['muted'], size=11))
    return _style(fig, "市场状态时间线 (绿=BULL牛市 | 黄=SHOCK震荡 | 红=BEAR熊市)", height=300)


# ========== 图表：月度热力图 ==========

def _fig_monthly(equity_df):
    eq = equity_df.copy()
    eq['date'] = pd.to_datetime(eq['date'])
    eq['year'] = eq['date'].dt.year
    eq['month'] = eq['date'].dt.month
    monthly = eq.groupby(['year', 'month'])['equity'].last().reset_index()
    # 全序列 pct_change: 按年分组会把每年1月变成 NaN 丢掉
    monthly['ret'] = monthly['equity'].pct_change() * 100
    monthly = monthly.dropna(subset=['ret'])
    monthly['label'] = monthly.apply(lambda r: f"{int(r['year'])}-{int(r['month']):02d}", axis=1)
    colors = [THEME['green'] if v >= 0 else THEME['red'] for v in monthly['ret']]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly['label'], y=monthly['ret'].round(2),
        marker_color=colors, name='月收益%',
        text=[f'{v:+.2f}%' for v in monthly['ret']],
        textposition='outside', textfont=dict(size=11, color=THEME['muted']),
        hovertemplate='%{x}: %{y:+.2f}%<extra></extra>',
    ))
    cumsum = monthly['ret'].sum()
    fig.add_annotation(
        text=f"累计: {cumsum:+.2f}%", xref='paper', yref='paper', x=0.98, y=0.95,
        showarrow=False, font=dict(color=THEME['green'] if cumsum >= 0 else THEME['red'], size=13),
        xanchor='right',
    )
    return _style(fig, "月度收益率", height=320)


# ========== 图表：Walk-Forward ==========

def _fig_walkforward(wf_df):
    fig = go.Figure()
    if wf_df is None or len(wf_df) == 0:
        return _style(fig, "Walk-Forward 分段收益 (无数据)")
    rets = wf_df['ret_pct'].astype(float).values
    dds = wf_df['max_dd_pct'].astype(float).values
    sharpe = wf_df['sharpe'].astype(float).values
    labels = [f"段{r['seg']}\n{r['start'][5:]}~{r['end'][5:]}" for _, r in wf_df.iterrows()]
    colors_bar = [THEME['green'] if v >= 0 else THEME['red'] for v in rets]
    fig.add_trace(go.Bar(x=labels, y=rets, marker_color=colors_bar, name='段收益%',
                          text=[f'{v:+.2f}%' for v in rets], textposition='outside',
                          textfont=dict(size=11, color=THEME['muted']),
                          hovertemplate='%{x}<br>收益: %{y:+.2f}%<br>回撤: %{customdata[0]:.2f}%<br>夏普: %{customdata[1]:.2f}<extra></extra>',
                          customdata=np.column_stack([dds, sharpe])))
    pos = (rets > 0).sum()
    n = len(rets)
    max_dd = dds.min()
    verdict = "✅ 达标 (2/3正收益, 无单段>15%回撤)" if pos >= 2 and max_dd > -15 else "⚠️ 未达标"
    ann = f"{n}段中 {pos}段正收益 ({pos/n*100:.0f}%) | 均收益 {rets.mean():+.2f}% | {verdict}"
    fig.add_annotation(text=ann, xref='paper', yref='paper', x=0.5, y=1.08, showarrow=False, font=dict(color=THEME['muted'], size=11))
    return _style(fig, "Walk-Forward 滚动验证", height=320)


# ========== 图表：交易流水表（HTML） ==========

def _html_trade_table(trades_df, name_map, equity_df):
    """生成完整交易流水表：可排序、可搜索、同花顺跳转"""
    if trades_df is None or len(trades_df) == 0:
        return '<div class="empty-msg">暂无交易记录</div>'

    sells = trades_df[trades_df['action'] == 'SELL'].copy()
    buys = trades_df[trades_df['action'] == 'BUY'].copy()

    rows = []
    for _, sr in sells.iterrows():
        code = sr['code']
        name = name_map.get(code, '???')
        # 找对应买入
        bm = buys[(buys['code'] == code) & (buys['date'] <= sr['date'])]
        if len(bm) > 0:
            br = bm.iloc[-1]
            buy_date = br['date']
            buy_price = br['price']
            hold_days = str((pd.to_datetime(sr['date']) - pd.to_datetime(buy_date)).days)
        else:
            buy_date = '-'
            buy_price = '-'
            hold_days = '-'

        pnl = sr['pnl'] if pd.notna(sr['pnl']) else 0
        pnl_pct = sr['pnl_pct'] if pd.notna(sr['pnl_pct']) else 0
        reason = sr['reason'] if pd.notna(sr['reason']) else '-'

        # 战法分类
        tactic = _classify_tactic(reason)

        cls = 'win' if pnl > 0 else 'loss'
        ths_link = THS_URL.format(code=code.lstrip('0'))

        rows.append({
            'cls': cls,
            'sell_date': sr['date'][5:] if len(sr['date']) > 5 else sr['date'],
            'code': code,
            'name': name,
            'ths_link': ths_link,
            'buy_date': buy_date[5:] if len(str(buy_date)) > 5 else buy_date,
            'buy_price': f"{float(buy_price):.2f}" if isinstance(buy_price, (int, float)) else str(buy_price),
            'sell_price': f"{float(sr['price']):.2f}",
            'pnl': f"{pnl:+.0f}",
            'pnl_pct': f"{pnl_pct:+.1f}%",
            'hold_days': hold_days,
            'reason': reason,
            'tactic': tactic,
            'shares': int(sr['shares']) if pd.notna(sr.get('shares')) else 0,
        })

    # 构建 HTML 表格，带简单 JS 排序
    header = ['卖出日', '代码', '名称', '买入日', '买入价', '卖出价', '股数', '盈亏', '%', '持(天)', '战法', '卖出理由']

    table_rows = []
    for r in rows:
        code_display = r['code']
        # 去掉前导零做同花顺链接
        code_clean = code_display.lstrip('0')
        ths_link = f"https://stockpage.10jqka.com.cn/{code_clean}/"
        # 东财链接按市场前缀: 6开头沪市sh, 其余深市sz
        mkt = 'sh' if code_display.startswith('6') else 'sz'
        east_link = EASTMONEY_URL.format(mkt=mkt, code=code_display)

        table_rows.append(f'''<tr class="{r['cls']}">
            <td>{r['sell_date']}</td>
            <td><a href="{ths_link}" target="_blank" title="同花顺">{code_display}</a> <a href="{east_link}" target="_blank" title="东方财富" style="font-size:10px;opacity:0.6;">📊</a></td>
            <td>{r['name']}</td>
            <td>{r['buy_date']}</td>
            <td>{r['buy_price']}</td>
            <td>{r['sell_price']}</td>
            <td>{r['shares']}</td>
            <td class="{r['cls']}">{r['pnl']}</td>
            <td class="{r['cls']}">{r['pnl_pct']}</td>
            <td>{r['hold_days']}</td>
            <td><span class="tactic-badge">{r['tactic']}</span></td>
            <td class="reason-cell">{r['reason']}</td>
        </tr>''')

    # 战法统计
    tactic_counts = {}
    for r in rows:
        t = r['tactic']
        if t not in tactic_counts:
            tactic_counts[t] = {'cnt': 0, 'pnl': 0, 'wins': 0}
        tactic_counts[t]['cnt'] += 1
        pnl_val = float(r['pnl']) if r['pnl'] != '-' else 0
        tactic_counts[t]['pnl'] += pnl_val
        if pnl_val > 0:
            tactic_counts[t]['wins'] += 1

    tactic_html = '<div class="tactic-stats">'
    for t, s in sorted(tactic_counts.items(), key=lambda x: x[1]['cnt'], reverse=True):
        wr = s['wins'] / s['cnt'] * 100 if s['cnt'] > 0 else 0
        tactic_html += f'<span class="tactic-item" style="border-color:{_tactic_color(t)};">{t}: {s["cnt"]}笔 | {s["wins"]}/{s["cnt"]}盈 | 合计{s["pnl"]:+.0f} | 胜率{wr:.0f}%</span>'
    tactic_html += '</div>'

    return f'''{tactic_html}
<div class="trade-table-wrap">
    <input type="text" id="tradeSearch" placeholder="🔍 搜索股票代码/名称/理由..." onkeyup="filterTrades()" class="trade-search">
    <table class="trade-table" id="tradeTable">
        <thead><tr>{''.join(f'<th onclick="sortTable({i})" class="sortable">{h} ▾</th>' for i, h in enumerate(header))}</tr></thead>
        <tbody>{"".join(table_rows)}</tbody>
    </table>
</div>
'''

SCRIPT_SORT = '''
<script>
let sortDir = {};
function sortTable(col) {
    const table = document.getElementById("tradeTable");
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    sortDir[col] = !sortDir[col];
    const dir = sortDir[col] ? 1 : -1;
    rows.sort((a, b) => {
        let va = a.cells[col].textContent.trim().replace(/[+%,]/g, "");
        let vb = b.cells[col].textContent.trim().replace(/[+%,]/g, "");
        let na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) return (na - nb) * dir;
        return va.localeCompare(vb) * dir;
    });
    rows.forEach(r => tbody.appendChild(r));
}
function filterTrades() {
    const q = document.getElementById("tradeSearch").value.toLowerCase();
    const rows = document.querySelectorAll("#tradeTable tbody tr");
    rows.forEach(r => {
        r.style.display = r.textContent.toLowerCase().includes(q) ? "" : "none";
    });
}
</script>
'''


def _classify_tactic(reason):
    """根据卖出理由分类战法"""
    if not reason or reason == '-':
        return '其他'
    r = reason.lower()
    if '止盈' in r and '移动' in r:
        return '移动止盈'
    elif '止盈' in r:
        if '20' in r or '15' in r or '25' in r:
            return '趋势持股'
        return '短线止盈'
    elif '止损' in r:
        return '破位止损'
    elif '清仓' in r:
        if 'shock' in r:
            return '环境切换'
        if 'bear' in r:
            return '熊市清仓'
        if '熔断' in r:
            return '熔断清仓'
        return '风控清仓'
    elif '信号转负' in r:
        return '信号离场'
    return '其他'


def _tactic_color(tactic):
    return {'趋势持股': THEME['green'], '短线止盈': THEME['accent'], '移动止盈': THEME['blue'],
            '破位止损': THEME['red'], '环境切换': THEME['yellow'], '熊市清仓': THEME['red'],
            '熔断清仓': THEME['red'], '信号离场': THEME['purple']}.get(tactic, THEME['muted'])


# ========== 图表：个股K线 + 买卖点 ==========

def _fig_stock_charts(trades_df, stock_pool, daily_dir, max_charts=6):
    """为每只交易过的股票生成K线图，标注买卖点"""
    if trades_df is None or len(trades_df) == 0:
        return []

    # 按总交易次数排序，选前 max_charts 只
    traded_codes = trades_df['code'].unique()
    code_stats = {}
    for c in traded_codes:
        sells = trades_df[(trades_df['code'] == c) & (trades_df['action'] == 'SELL')]
        pnl_total = sells['pnl'].sum() if len(sells) > 0 else 0
        code_stats[c] = {'n_sells': len(sells), 'pnl': pnl_total}

    top_codes = sorted(code_stats.keys(), key=lambda c: code_stats[c]['pnl'], reverse=True)[:max_charts]

    charts = []
    for code in top_codes:
        csv_path = os.path.join(daily_dir, f"{code}.csv")
        if not os.path.exists(csv_path):
            # try without leading zeros
            csv_path = os.path.join(daily_dir, f"{int(code)}.csv")
        if not os.path.exists(csv_path):
            continue

        df = pd.read_csv(csv_path)
        df['date'] = pd.to_datetime(df['date'])

        # 限制在交易日期范围
        stock_trades = trades_df[trades_df['code'] == code]
        t_dates = pd.to_datetime(stock_trades['date'].unique())
        if len(t_dates) > 0:
            t_min, t_max = t_dates.min() - pd.Timedelta(days=30), t_dates.max() + pd.Timedelta(days=10)
            df = df[(df['date'] >= t_min) & (df['date'] <= t_max)]

        name = stock_pool.get(code, '???')
        pnl_total = code_stats[code]['pnl']

        fig = _make_stock_chart(df, stock_trades, code, name, pnl_total)
        if fig is not None:
            charts.append((code, name, pnl_total, fig))

    return charts


def _make_stock_chart(df, trades_df, code, name, pnl_total):
    """单只股票K线图 + 均线 + 量能 + 买卖点标注"""
    fig = go.Figure()

    # K线
    fig.add_trace(go.Candlestick(
        x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name=name,
        increasing=dict(line=dict(color=THEME['red'], width=1), fillcolor=THEME['red']),
        decreasing=dict(line=dict(color=THEME['green'], width=1), fillcolor=THEME['green']),
        showlegend=False,
    ))

    # 均线
    for period, color, width in [(5, THEME['yellow'], 0.8), (20, THEME['purple'], 1.0), (60, THEME['blue'], 0.8)]:
        if len(df) >= period:
            ma = df['close'].rolling(period).mean()
            fig.add_trace(go.Scatter(
                x=df['date'], y=ma, mode='lines', name=f'MA{period}',
                line=dict(color=color, width=width, dash='solid'),
                showlegend=True,
            ))

    # 量能（柱子叠加在底部）
    if 'volume' in df.columns:
        vol_colors = [THEME['red'] if df['close'].iloc[i] >= df['open'].iloc[i] else THEME['green']
                      for i in range(len(df))]
        fig.add_trace(go.Bar(
            x=df['date'], y=df['volume'],
            name='成交量', marker=dict(color=vol_colors, opacity=0.3),
            yaxis='y2', showlegend=False,
        ))

    # 买卖点标记
    buys = trades_df[trades_df['action'] == 'BUY']
    sells = trades_df[trades_df['action'] == 'SELL']

    # 标注买入
    for _, br in buys.iterrows():
        bdate = pd.to_datetime(br['date'])
        bprice = br['price']
        fig.add_annotation(
            x=bdate, y=bprice, text='<b>B</b>', showarrow=True,
            arrowhead=2, arrowsize=1, arrowwidth=2, arrowcolor=THEME['green'],
            font=dict(color=THEME['green'], size=13), bgcolor='rgba(0,0,0,0.7)',
            borderpad=3, ax=0, ay=-30,
        )

    for _, sr in sells.iterrows():
        sdate = pd.to_datetime(sr['date'])
        sprice = sr['price']
        is_win = sr['pnl'] > 0 if pd.notna(sr.get('pnl')) else False
        color_s = THEME['green'] if is_win else THEME['red']
        label = 'S✓' if is_win else 'S✗'
        fig.add_annotation(
            x=sdate, y=sprice, text=f'<b>{label}</b>', showarrow=True,
            arrowhead=2, arrowsize=1, arrowwidth=2, arrowcolor=color_s,
            font=dict(color=color_s, size=13), bgcolor='rgba(0,0,0,0.7)',
            borderpad=3, ax=0, ay=30,
        )

    color_indicator = THEME['green'] if pnl_total >= 0 else THEME['red']

    fig.update_layout(
        title=dict(text=f"{code} {name}  <span style='color:{color_indicator};font-size:13px;'>累计{pnl_total:+.0f}</span>",
                   font=dict(color=THEME['text'], size=14), x=0.01),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=THEME['muted'], size=11),
        margin=dict(l=55, r=22, t=50, b=40),
        height=440,
        xaxis=dict(gridcolor='rgba(255,255,255,0.06)', linecolor='rgba(255,255,255,0.12)',
                   rangeslider=dict(visible=False), type='date'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.06)', linecolor='rgba(255,255,255,0.12)',
                   title=dict(text='价格', font=dict(size=10)), side='right'),
        yaxis2=dict(
            title=dict(text='量', font=dict(size=10)),
            overlaying='y', side='left', showgrid=False,
            # scale volume to 20% of price axis
            range=[0, df['volume'].max() * 5] if 'volume' in df.columns else None,
        ),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0, font=dict(size=10)),
        hovermode='x unified',
    )

    return fig


# ========== 图表：因子权重 ==========

def _fig_weights(equity_df):
    from src.utils.market_regime import MarketRegime
    regime = MarketRegime()
    weights_all = {r: regime.get_factor_weights(r) for r in ['BULL', 'SHOCK', 'BEAR']}
    last_regime = str(equity_df['regime'].iloc[-1]) if 'regime' in equity_df.columns else 'SHOCK'
    w = weights_all.get(last_regime, weights_all['SHOCK'])
    factors = list(w.keys())
    vals = list(w.values())
    colors = [THEME['green'] if v >= 0 else THEME['red'] for v in vals]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=factors, y=vals, marker_color=colors, name=f'{last_regime}权重',
        text=[f'{v:+.2f}' for v in vals], textposition='outside',
        textfont=dict(size=10, color=THEME['muted']),
    ))
    fig.update_layout(xaxis_tickangle=-35, showlegend=False)
    return _style(fig, f"因子权重 (最近市场状态: {last_regime})", height=300)


# ========== 战法收益分布图 ==========

def _fig_tactic_performance(trades_df):
    """按战法分类展示收益分布"""
    fig = go.Figure()
    if trades_df is None or len(trades_df) == 0:
        return _style(fig, "战法收益分布 (无数据)")

    sells = trades_df[trades_df['action'] == 'SELL'].copy()
    if len(sells) == 0:
        return _style(fig, "战法收益分布 (无平仓)")

    sells['tactic'] = sells['reason'].apply(_classify_tactic)
    tactics = sells['tactic'].unique()

    for tactic in tactics:
        sub = sells[sells['tactic'] == tactic]
        fig.add_trace(go.Box(
            y=sub['pnl_pct'], name=tactic,
            marker_color=_tactic_color(tactic),
            boxmean='sd',
        ))

    fig.add_hline(y=0, line_dash='solid', line_color=THEME['muted'], opacity=0.4)
    return _style(fig, "各战法盈亏分布 (箱线图)", height=340)


# ========== 周度收益热力图 ==========

def _fig_weekly_heatmap(equity_df):
    """日历热力图：按周看收益"""
    eq = equity_df.copy()
    eq['date'] = pd.to_datetime(eq['date'])
    eq['week'] = eq['date'].dt.isocalendar().week.astype(int)
    eq['year'] = eq['date'].dt.isocalendar().year.astype(int)
    eq['day_of_week'] = eq['date'].dt.dayofweek  # 0=Mon

    weekly = eq.groupby(['year', 'week'])['equity'].last().reset_index()
    # 全序列 pct_change: 按年分组会把每年第一个 ISO 周丢掉
    weekly['wret'] = weekly['equity'].pct_change() * 100
    weekly = weekly.dropna(subset=['wret'])

    colors = [[0, THEME['red']], [0.5, THEME['bg']], [1, THEME['green']]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[f"{int(r['year'])}-W{int(r['week']):02d}" for _, r in weekly.iterrows()],
        y=weekly['wret'].round(2),
        marker=dict(
            color=weekly['wret'],
            colorscale=colors,
            cmin=-5, cmax=5,
            colorbar=dict(title='周收益%', thickness=15, x=1.01),
        ),
        name='周收益',
        hovertemplate='%{x}: %{y:+.2f}%<extra></extra>',
    ))
    return _style(fig, "周度收益率热力图", height=280)


# ========== HTML 模板 ==========

CSS_V2 = f'''
<style>
  :root{{ --bg:{THEME['bg']}; --card:{THEME['card']}; --border:{THEME['border']}; --text:{THEME['text']};
          --muted:{THEME['muted']}; --accent:{THEME['accent']}; --green:{THEME['green']};
          --red:{THEME['red']}; --yellow:{THEME['yellow']}; }}
  *{{ box-sizing:border-box; }}
  body{{ margin:0; background:var(--bg); color:var(--text);
         font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,'Microsoft YaHei',sans-serif; }}
  .wrap{{ max-width:1400px; margin:0 auto; padding:28px 22px 60px; }}
  header{{ border-bottom:1px solid var(--border); padding-bottom:18px; margin-bottom:24px; }}
  header h1{{ margin:0 0 6px; font-size:26px; letter-spacing:.5px; }}
  header .sub{{ color:var(--muted); font-size:13px; line-height:1.6; }}
  .kpis{{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:26px; }}
  .kpi{{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px; transition:border-color .2s; }}
  .kpi:hover{{ border-color:var(--accent); }}
  .kpi .label{{ color:var(--muted); font-size:11px; margin-bottom:8px; text-transform:uppercase; letter-spacing:.5px; }}
  .kpi .val{{ font-size:28px; font-weight:700; }}
  .kpi .sub-val{{ font-size:12px; color:var(--muted); margin-top:4px; }}
  .pos{{ color:var(--green); }} .neg{{ color:var(--red); }}
  .grid{{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
  .card{{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:8px 10px; overflow:hidden; }}
  .card.full{{ grid-column:1 / -1; }}
  .card h3{{ margin:0 0 4px; color:var(--muted); font-size:12px; font-weight:500; padding:6px 8px 0; }}
  .section-title{{ grid-column:1 / -1; color:var(--accent); font-size:16px; font-weight:600; padding:20px 0 4px; border-bottom:1px solid var(--border); margin-bottom:4px; }}
  .note{{ margin-top:26px; color:var(--muted); font-size:12px; line-height:1.7;
          background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 20px; }}
  .note b{{ color:var(--text); }}
  code{{ background:#21262d; padding:1px 6px; border-radius:4px; color:var(--accent); }}

  /* 交易表格 */
  .trade-table-wrap{{ overflow-x:auto; margin-top:12px; }}
  .trade-search{{ width:100%; padding:10px 14px; margin-bottom:12px; background:var(--card); border:1px solid var(--border);
                   border-radius:8px; color:var(--text); font-size:13px; outline:none; }}
  .trade-search:focus{{ border-color:var(--accent); }}
  .trade-table{{ width:100%; border-collapse:collapse; font-size:12px; }}
  .trade-table th{{ background:var(--card); color:var(--muted); padding:10px 8px; text-align:left; font-weight:500;
                     border-bottom:2px solid var(--border); cursor:pointer; user-select:none; white-space:nowrap; position:sticky; top:0; }}
  .trade-table th:hover{{ color:var(--accent); }}
  .trade-table td{{ padding:8px; border-bottom:1px solid rgba(255,255,255,0.04); white-space:nowrap; }}
  .trade-table tr:hover td{{ background:rgba(79,209,197,0.04); }}
  .trade-table tr.win td{{  }}
  .trade-table tr.loss td{{  }}
  .trade-table td.win{{ color:var(--green); font-weight:600; }}
  .trade-table td.loss{{ color:var(--red); font-weight:600; }}
  .trade-table a{{ color:var(--accent); text-decoration:none; }}
  .trade-table a:hover{{ text-decoration:underline; }}
  .reason-cell{{ max-width:200px; white-space:normal!important; font-size:11px; color:var(--muted); }}
  .tactic-badge{{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:10px; background:rgba(255,255,255,0.06); border:1px solid var(--border); }}
  .tactic-stats{{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }}
  .tactic-item{{ padding:4px 12px; border-radius:6px; font-size:11px; background:rgba(255,255,255,0.03); border:1px solid; }}
  .empty-msg{{ color:var(--muted); padding:40px; text-align:center; }}

  @media(max-width:1000px){{ .kpis{{grid-template-columns:repeat(2,1fr);}} .grid{{grid-template-columns:1fr;}} }}
</style>
'''


def _kpi_card(label, value, cls='', sub=''):
    sub_html = f'<div class="sub-val">{sub}</div>' if sub else ''
    return f'<div class="kpi"><div class="label">{label}</div><div class="val {cls}">{value}</div>{sub_html}</div>'


def _header(stats):
    total = stats.get('总收益率', 0.0)
    dd = stats.get('最大回撤', 0.0)
    sharpe = stats.get('夏普比率', 0.0)
    win = stats.get('胜率', 0.0)
    annual = stats.get('年化收益', 0.0)
    calmar = stats.get('卡玛比率', 0.0)
    n_trades = stats.get('总交易次数', 0)
    max_win = stats.get('最大单笔盈利', 0)
    max_loss = stats.get('最大单笔亏损', 0)
    plr = stats.get('盈亏比', 0)
    end_val = stats.get('期末资金', 100000)
    max_dd_dur = stats.get('最大回撤持续', 0)

    kpis = "".join([
        _kpi_card("总收益率", f"{total:+.2f}%", "pos" if total >= 0 else "neg",
                  f"年化 {annual:+.1f}%"),
        _kpi_card("最大回撤", f"{dd:.2f}%", "neg",
                  f"持续 {max_dd_dur} 天"),
        _kpi_card("夏普比率", f"{sharpe:.2f}", "pos" if sharpe >= 0 else "neg",
                  f"卡玛 {calmar:.2f}"),
        _kpi_card("胜率/盈亏比", f"{win:.1f}% / {plr:.2f}", "pos" if win >= 50 else "neg",
                  f"{n_trades}笔 | 期末¥{end_val:,.0f}"),
    ])
    now = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    return f'''
<header>
  <h1>🔬 A股量化策略 · 回测仪表盘 v2</h1>
  <div class="sub">
    毛选思想驱动 · 多因子+市场状态自适应 &nbsp;|&nbsp; 生成于 {now} &nbsp;|&nbsp; 
    股票池: 主板流动性前800只 &nbsp;|&nbsp; 手续费已含(万2.5+千0.5+千1滑点)
  </div>
</header>
<div class="kpis">{kpis}</div>
'''


def _card(title, div_html, full=False):
    cls = "card full" if full else "card"
    return f'<div class="{cls}"><h3>{title}</h3>{div_html}</div>'


_NOTE_V2 = f'''
<div class="note">
<b>⚔️ 毛选思想方法</b><br>
<span style="color:{THEME['green']};">● 调查研究</span>：每日判断市场四维状态（MA趋势/波动率/近期涨跌/慢牛结构），不凭感觉<br>
<span style="color:{THEME['accent']};">● 抓主要矛盾</span>：牛市动量为主（歼灭战）、震荡反转为主（游击战）、熊市空仓保存实力<br>
<span style="color:{THEME['yellow']};">● 集中优势兵力</span>：横截面z-score标准化+分位数筛选，只买前20%最强信号<br>
<span style="color:{THEME['purple']};">● 保存实力</span>：-7%硬止损、+15%止盈、移动止盈、连亏冷却、组合熔断、指数破位清仓<br>
<span style="color:{THEME['blue']};">● 实事求是</span>：市场状态判断量化四维度+慢牛专项+趋势确认，不为任何预设结论服务<br>
<span style="color:{THEME['red']};">⚠ 样本内回测 + walk-forward 滚动验证，不构成投资建议。过去表现不代表未来收益。</span>
</div>
'''


# ========== 主函数 ==========

def generate_report():
    # 加载数据
    equity = _load_equity()
    if equity is None:
        print("[!] 未找到回测结果，请先运行: python main.py backtest")
        return None

    trades = _load_trades()
    wf_df = _load_walkforward()
    stock_pool = _load_stock_pool()

    stats = _calc_stats(equity, trades)
    idx_norm = _get_benchmark(equity)

    # 生成图表
    figs = {}
    figs['equity'] = _fig_equity(equity, idx_norm, trades)
    figs['drawdown'] = _fig_drawdown(equity)
    figs['regime'] = _fig_regime(equity)
    figs['monthly'] = _fig_monthly(equity)
    figs['weekly'] = _fig_weekly_heatmap(equity)
    figs['walkforward'] = _fig_walkforward(wf_df)
    figs['weights'] = _fig_weights(equity)
    figs['tactic'] = _fig_tactic_performance(trades)

    # 交易流水表
    trade_table_html = _html_trade_table(trades, stock_pool, equity)

    # 个股K线图
    stock_charts = _fig_stock_charts(trades, stock_pool, os.path.join(DATA_DIR, 'daily'), max_charts=8)

    # 组装 HTML
    parts = [CSS_V2, _header(stats), SCRIPT_SORT]

    # KPI 卡片已在上方
    first = True
    def add_fig(key, title, full=False):
        nonlocal first
        div = pio.to_html(figs[key], include_plotlyjs=('cdn' if first else False), full_html=False)
        first = False
        parts.append(_card(title, div, full))

    add_fig('equity', '📈 策略净值 vs 上证指数 (▲买入 | ▼卖出: 绿=盈利 红=亏损)', True)
    add_fig('drawdown', '📉 回撤曲线', True)
    add_fig('regime', '🏁 市场状态时间线 (绿=BULL | 黄=SHOCK | 红=BEAR)', True)
    add_fig('monthly', '📅 月度收益率', False)
    add_fig('weekly', '📊 周度收益率热力图', False)
    add_fig('walkforward', '🔬 Walk-Forward 滚动验证 (策略稳定性)', True)
    add_fig('tactic', '🎯 各战法盈亏分布 (箱线图)', True)

    # 交易流水表
    parts.append(f'<div class="section-title">📋 完整交易流水 (点击表头排序 | 搜索框过滤 | 代码链接→同花顺)</div>')
    parts.append(f'<div class="card full">{trade_table_html}</div>')

    # 个股K线
    if stock_charts:
        parts.append(f'<div class="section-title">📊 个股K线图 (B=买入 S✓=盈利卖出 S✗=亏损卖出 | MA5/MA20/MA60+量能)</div>')
        parts.append('<div class="grid">')
        for code, name, pnl, fig in stock_charts:
            div = pio.to_html(fig, include_plotlyjs=False, full_html=False)
            # 同花顺链接
            code_clean = code.lstrip('0')
            ths_link = THS_URL.format(code=code_clean)
            color_indicator = THEME['green'] if pnl >= 0 else THEME['red']
            title = f'{code} {name} <a href="{ths_link}" target="_blank" style="font-size:10px;color:var(--accent);">同花顺↗</a> <span style="color:{color_indicator};">累计{pnl:+.0f}</span>'
            parts.append(f'<div class="card"><h3>{title}</h3>{div}</div>')
        parts.append('</div>')

    # 因子权重
    add_fig('weights', '⚖️ 因子权重', True)

    parts.append(_NOTE_V2)
    parts.append("</div></body></html>")

    html = "\n".join(parts)

    os.makedirs(RESULT_DIR, exist_ok=True)
    out = os.path.join(RESULT_DIR, f"report_{dt.datetime.now():%Y%m%d_%H%M}.html")
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] 专业可视化报告已生成: {out}")
    print(f"     文件大小: {os.path.getsize(out)/1024/1024:.1f} MB")
    return out


if __name__ == "__main__":
    generate_report()
