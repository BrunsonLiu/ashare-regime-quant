/* ============================================
   情绪终端 · 应用逻辑
   依赖 shared.js(布局/数据/工具) 与 charts.js(图表)
   ============================================ */

const App = {
  data: null,
  currentRange: 'all',

  async init() {
    this.data = await DataLoader.loadAll();
    if (!this.data.sentiment) {
      showError('请先运行: python main.py gen-webdata');
      return;
    }

    this.updateFooter();
    this.renderOverview();
    this.renderCycle();
    this.renderBacktest();
    this.renderTrades();
    this.renderWalkforward();

    // hash 路由: 支持 index.html#tab-backtest 跨页直达
    bindTabRoute('tab-', (name) => this.switchTab(name));
  },

  updateFooter() {
    const s = this.data.sentiment;
    const rangeEl = document.getElementById('data-range');
    if (s && s.stats && rangeEl) {
      rangeEl.textContent = `${s.stats.date_start} ~ ${s.stats.date_end} (${s.stats.total_days}天)`;
    }
  },

  /** 切换页签: 同时同步 hash, 保证刷新后停在同一页 */
  switchTab(name) {
    const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
    if (!btn) return;
    document.querySelectorAll('.tab-btn[data-tab]').forEach(b => {
      b.classList.toggle('active', b === btn);
    });
    document.querySelectorAll('.tab-content').forEach(t => {
      t.classList.toggle('active', t.id === `tab-${name}`);
    });
    // 隐藏状态下 Plotly 量不到宽度, 切回来必须重绘
    window.dispatchEvent(new Event('resize'));
  },

  // ========== Tab: 情绪总览 ==========
  renderOverview() {
    const s = this.data.sentiment;
    if (!s) return;

    const last = s.dates.length - 1;
    const todayZt = s.zt_count[last];
    const todayZr = s.zhaban_rate[last];
    const todayLb = s.lianban_height[last];
    const todaySb = s.shouban[last];

    const q = s.quantiles.zt_count;
    let status = '正常', cls = '';
    if (todayZt < q.p20) { status = '冰点区'; cls = 'alert'; }
    else if (todayZt > q.p80) { status = '高潮区'; cls = 'warn'; }

    const kpiHtml = `
      <div class="kpi-card">
        <div class="kpi-label">最新日期</div>
        <div class="kpi-value is-date">${s.dates[last]}</div>
        <div class="kpi-sub">${status}</div>
      </div>
      <div class="kpi-card ${cls}">
        <div class="kpi-label">涨停家数</div>
        <div class="kpi-value">${todayZt}</div>
        <div class="kpi-sub">P20=${q.p20} · P80=${q.p80} · 中位=${s.quantiles.zt_count.p50}</div>
      </div>
      <div class="kpi-card ${todayZr > s.quantiles.zhaban_rate.p80 ? 'warn' : ''}">
        <div class="kpi-label">炸板率</div>
        <div class="kpi-value">${(todayZr * 100).toFixed(1)}%</div>
        <div class="kpi-sub">P80=${(s.quantiles.zhaban_rate.p80 * 100).toFixed(0)}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">最高连板</div>
        <div class="kpi-value">${todayLb}<span style="font-size:12px;font-weight:400;color:var(--text-3)"> 板</span></div>
        <div class="kpi-sub">P90=${s.quantiles.lianban_height.p90}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">首板家数</div>
        <div class="kpi-value">${todaySb}</div>
        <div class="kpi-sub">占比 ${(s.shouban_ratio[last] * 100).toFixed(0)}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">日均涨停 (3年)</div>
        <div class="kpi-value">${s.stats.zt_mean}</div>
        <div class="kpi-sub">中位 ${s.stats.zt_median}</div>
      </div>`;
    document.getElementById('kpi-row').innerHTML = kpiHtml;

    chartZtZhaban(this.data, this.currentRange);
    chartLianbanHeight(this.data);
    chartLianban(this.data);
    chartShouban(this.data);
    chartMonthlyHeat(this.data);

    document.querySelectorAll('.range-btn[data-range]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.range-btn[data-range]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.currentRange = btn.dataset.range;
        chartZtZhaban(this.data, this.currentRange);
      });
    });
  },

  // ========== Tab: 周期分析 ==========
  renderCycle() {
    const mk = this.data.markers;
    const s = this.data.sentiment;
    if (!mk) return;

    const rs = mk.reversal_stats;
    document.getElementById('cycle-kpi').innerHTML = `
      <div class="kpi-card alert">
        <div class="kpi-label">冰点总天数</div>
        <div class="kpi-value">${rs.total_bing}</div>
        <div class="kpi-sub">3年共 ${s.stats.total_days} 天</div>
      </div>
      <div class="kpi-card good">
        <div class="kpi-label">3日反转率</div>
        <div class="kpi-value">${(rs.rev_3d_rate * 100).toFixed(0)}%</div>
        <div class="kpi-sub">冰点后3日涨停回升</div>
      </div>
      <div class="kpi-card good">
        <div class="kpi-label">5日反转率</div>
        <div class="kpi-value">${(rs.rev_5d_rate * 100).toFixed(0)}%</div>
        <div class="kpi-sub">冰点后5日涨停回升</div>
      </div>
      <div class="kpi-card ${rs.avg_3d > 0 ? 'good' : 'alert'}">
        <div class="kpi-label">3日平均变化</div>
        <div class="kpi-value">${rs.avg_3d > 0 ? '+' : ''}${rs.avg_3d}</div>
        <div class="kpi-sub">涨停数变化</div>
      </div>`;

    const revHtml = `
      <div class="stat-row">
        <span class="stat-label">冰点判定标准</span>
        <span class="stat-val plain">涨停数 &lt; P20(${mk.thresholds.zt_p20}) 或炸板率 &gt; P80(${(mk.thresholds.zh_p80 * 100).toFixed(0)}%)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">高潮判定标准</span>
        <span class="stat-val plain">涨停数 &gt; P80(${mk.thresholds.zt_p80})</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">冰点总天数</span>
        <span class="stat-val red">${rs.total_bing}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">3日反转成功</span>
        <span class="stat-val green">${rs.rev_3d} / ${rs.total_bing} (${(rs.rev_3d_rate * 100).toFixed(0)}%)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">5日反转成功</span>
        <span class="stat-val green">${rs.rev_5d} / ${rs.total_bing} (${(rs.rev_5d_rate * 100).toFixed(0)}%)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">3日平均涨停变化</span>
        <span class="stat-val ${rs.avg_3d > 0 ? 'red' : 'green'}">${rs.avg_3d > 0 ? '+' : ''}${rs.avg_3d}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">5日平均涨停变化</span>
        <span class="stat-val ${rs.avg_5d > 0 ? 'red' : 'green'}">${rs.avg_5d > 0 ? '+' : ''}${rs.avg_5d}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">高潮总天数</span>
        <span class="stat-val yellow">${mk.gao_days.length}</span>
      </div>`;
    document.getElementById('reversal-stats').innerHTML = revHtml;

    chartBingGao(this.data);
    chartYearly(this.data);
    chartEchelon(this.data);
  },

  // ========== Tab: 回测绩效 ==========
  renderBacktest() {
    const bt = this.data.backtest;
    if (!bt) {
      document.getElementById('bt-kpi').innerHTML =
        '<div class="kpi-card"><div class="kpi-label">回测数据</div><div class="kpi-value is-date">暂无</div></div>';
      return;
    }

    const st = bt.stats;
    document.getElementById('bt-kpi').innerHTML = `
      <div class="kpi-card ${st.total_return >= 0 ? 'good' : 'alert'}">
        <div class="kpi-label">总收益率</div>
        <div class="kpi-value q-${st.total_return >= 0 ? 'up' : 'down'}">${st.total_return > 0 ? '+' : ''}${st.total_return}%</div>
        <div class="kpi-sub">${st.days} 个交易日</div>
      </div>
      <div class="kpi-card alert">
        <div class="kpi-label">最大回撤</div>
        <div class="kpi-value">${st.max_drawdown}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">初始资金</div>
        <div class="kpi-value">${st.initial_capital.toLocaleString()}</div>
      </div>
      <div class="kpi-card good">
        <div class="kpi-label">最终净值</div>
        <div class="kpi-value">${st.final_equity.toLocaleString()}</div>
      </div>`;

    chartEquity(this.data);
    chartDrawdown(this.data);
    chartRegime(this.data);
  },

  // ========== Tab: 交易流水 ==========
  renderTrades() {
    const tr = this.data.trades;
    if (!tr) {
      document.getElementById('trade-body').innerHTML =
        `<tr><td colspan="20"><div class="empty-state"><div class="empty-title">暂无交易数据</div></div></td></tr>`;
      return;
    }

    document.getElementById('trade-header').innerHTML =
      tr.columns.map(c => `<th data-col="${c}">${c}</th>`).join('');

    this._trades = tr;
    this._filteredTrades = tr.rows.map((r, i) => ({ row: r, idx: i }));
    this.renderTradeRows();

    document.getElementById('trade-search').addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      this._filteredTrades = tr.rows
        .map((r, i) => ({ row: r, idx: i }))
        .filter(({ row }) => row.some(v => String(v).toLowerCase().includes(q)));
      this.renderTradeRows();
    });

    document.querySelectorAll('[data-sort]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-sort]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const sortKey = btn.dataset.sort;
        const colIdx = tr.columns.indexOf(sortKey);
        if (colIdx < 0) return;
        this._filteredTrades.sort((a, b) => {
          const va = a.row[colIdx], vb = b.row[colIdx];
          // 日期列按字符串比较, parseFloat 会把 '2026-02-26' 截成年份
          if (sortKey === 'date') return String(vb).localeCompare(String(va));
          const na = parseFloat(va), nb = parseFloat(vb);
          if (isNaN(na) && isNaN(nb)) return 0;
          if (isNaN(na)) return 1;
          if (isNaN(nb)) return -1;
          return nb - na;
        });
        this.renderTradeRows();
      });
    });
  },

  renderTradeRows() {
    const cols = this._trades.columns;
    const html = this._filteredTrades.map(({ row }) => {
      const cells = row.map((v, i) => {
        const col = cols[i];
        let cls = '';
        if (col === 'action') cls = v === 'BUY' ? 'buy' : 'sell';
        else if (col === 'pnl' && v !== null && v !== '') {
          const num = parseFloat(v);
          cls = num > 0 ? 'profit' : num < 0 ? 'loss' : '';
        }
        const display = v === null || v === undefined ? ''
          : (typeof v === 'number' ? v.toFixed(2) : String(v));
        return `<td class="${cls}">${display}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
    document.getElementById('trade-body').innerHTML = html ||
      `<tr><td colspan="20"><div class="empty-state"><div class="empty-title">无匹配记录</div></div></td></tr>`;
  },

  // ========== Tab: 滚动验证 ==========
  renderWalkforward() {
    const wf = this.data.walkforward;
    if (!wf) return;

    chartWalkforward(this.data);

    const cols = ['seg', 'start', 'end', 'ret_pct', 'max_dd_pct', 'sharpe', 'win_rate', 'n_trades'];
    const labels = ['段', '开始', '结束', '收益%', '最大回撤%', '夏普', '胜率%', '交易数'];
    const numeric = new Set(['ret_pct', 'max_dd_pct', 'sharpe', 'win_rate']);

    let html = '<table><thead><tr>';
    labels.forEach((l, i) => {
      html += `<th class="${numeric.has(cols[i]) ? 'num' : ''}">${l}</th>`;
    });
    html += '</tr></thead><tbody>';
    wf.forEach(s => {
      html += '<tr>';
      cols.forEach(c => {
        let cls = numeric.has(c) ? 'num' : '';
        if (c === 'ret_pct') cls += ` ${s[c] >= 0 ? 'profit' : 'loss'}`;
        if (c === 'max_dd_pct') cls += ' loss';
        html += `<td class="${cls}">${s[c]}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';

    document.getElementById('wf-table-wrap').innerHTML = html;
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());