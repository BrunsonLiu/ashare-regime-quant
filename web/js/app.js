/* ============================================
   主应用 · 路由 + KPI + 表格 + 交互
   ============================================ */

const App = {
  data: null,
  currentRange: 'all',

  async init() {
    this.data = await DataLoader.loadAll();
    if (!this.data.sentiment) {
      this.showError('数据加载失败，请先运行: python src/sentiment/gen_webdata.py');
      return;
    }
    
    this.updateClock();
    setInterval(() => this.updateClock(), 1000);
    this.updateMarketStatus();
    this.updateFooter();
    
    this.renderOverview();
    this.renderCycle();
    this.renderBacktest();
    this.renderTrades();
    this.renderWalkforward();
  },

  updateClock() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    document.getElementById('clock').textContent = `${h}:${m}:${s}`;
  },

  updateMarketStatus() {
    const now = new Date();
    const day = now.getDay();
    const h = now.getHours();
    const m = now.getMinutes();
    const hm = h * 60 + m;
    
    const isWeekday = day >= 1 && day <= 5;
    const isOpen = isWeekday && ((hm >= 570 && hm <= 690) || (hm >= 780 && hm <= 900));
    
    const dot = document.getElementById('market-status');
    const label = document.getElementById('market-label');
    
    if (isOpen) {
      dot.className = 'market-status open';
      label.textContent = 'OPEN';
    } else {
      dot.className = 'market-status closed';
      label.textContent = 'CLOSED';
    }
  },

  updateFooter() {
    const s = this.data.sentiment;
    if (s && s.stats) {
      const rangeEl = document.getElementById('data-range');
      if (rangeEl) {
        rangeEl.textContent = `${s.stats.date_start} ~ ${s.stats.date_end} (${s.stats.total_days}天)`;
      }
    }
    const updEl = document.getElementById('last-update');
    if (updEl) updEl.textContent = `Updated: ${new Date().toLocaleString('zh-CN')}`;
  },

  showError(msg) {
    document.getElementById('main').innerHTML =
      `<div style="text-align:center;padding:80px;color:#ff5c5c;font-family:monospace;">⚠ ${msg}</div>`;
  },

  // Tab 切换由 index.html 内联脚本处理(按钮高亮依赖内联样式),此处不再重复绑定

  // ========== Tab: Overview ==========
  renderOverview() {
    const s = this.data.sentiment;
    if (!s) return;

    const last = s.dates.length - 1;
    const todayZt = s.zt_count[last];
    const todayZr = s.zhaban_rate[last];
    const todayLb = s.lianban_height[last];
    const todaySb = s.shouban[last];
    
    // 判断状态
    const p20 = s.quantiles.zt_count.p20;
    const p80 = s.quantiles.zt_count.p80;
    let status = '正常', cls = '';
    if (todayZt < p20) { status = '冰点'; cls = 'alert'; }
    else if (todayZt > p80) { status = '高潮'; cls = 'good'; }
    
    const kpiHtml = `
      <div class="kpi-card ${cls}">
        <div class="kpi-label">最新日期</div>
        <div class="kpi-value" style="font-size:16px">${s.dates[last]}</div>
        <div class="kpi-sub">${status}</div>
      </div>
      <div class="kpi-card ${cls}">
        <div class="kpi-label">涨停家数</div>
        <div class="kpi-value">${todayZt}</div>
        <div class="kpi-sub">P20=${p20} | P80=${p80} | 中位=${s.quantiles.zt_count.p50}</div>
      </div>
      <div class="kpi-card ${todayZr > s.quantiles.zhaban_rate.p80 ? 'alert' : ''}">
        <div class="kpi-label">炸板率</div>
        <div class="kpi-value">${(todayZr * 100).toFixed(1)}%</div>
        <div class="kpi-sub">P80=${(s.quantiles.zhaban_rate.p80 * 100).toFixed(0)}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">连板高度</div>
        <div class="kpi-value">${todayLb}</div>
        <div class="kpi-sub">P90=${s.quantiles.lianban_height.p90}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">首板家数</div>
        <div class="kpi-value">${todaySb}</div>
        <div class="kpi-sub">占比=${(s.shouban_ratio[last] * 100).toFixed(0)}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">日均涨停(3年)</div>
        <div class="kpi-value">${s.stats.zt_mean}</div>
        <div class="kpi-sub">中位=${s.stats.zt_median}</div>
      </div>
    `;
    document.getElementById('kpi-row').innerHTML = kpiHtml;

    chartZtZhaban(this.data, this.currentRange);
    chartLianban(this.data);
    chartShouban(this.data);
    chartMonthlyHeat(this.data);

    // 范围按钮
    document.querySelectorAll('.range-btn[data-range]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.range-btn[data-range]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.currentRange = btn.dataset.range;
        chartZtZhaban(this.data, this.currentRange);
      });
    });
  },

  // ========== Tab: Cycle ==========
  renderCycle() {
    const mk = this.data.markers;
    const s = this.data.sentiment;
    if (!mk) return;

    const rs = mk.reversal_stats;
    const kpiHtml = `
      <div class="kpi-card alert">
        <div class="kpi-label">冰点总天数</div>
        <div class="kpi-value">${rs.total_bing}</div>
        <div class="kpi-sub">3年共${s.stats.total_days}天</div>
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
      <div class="kpi-card">
        <div class="kpi-label">3日平均变化</div>
        <div class="kpi-value">${rs.avg_3d > 0 ? '+' : ''}${rs.avg_3d}</div>
        <div class="kpi-sub">涨停数变化</div>
      </div>
    `;
    document.getElementById('cycle-kpi').innerHTML = kpiHtml;

    // 反转统计表
    const revHtml = `
      <div class="stat-row">
        <span class="stat-label">冰点判定标准</span>
        <span class="stat-val yellow">涨停数 < P20(${mk.thresholds.zt_p20}) 或 炸板率 > P80(${(mk.thresholds.zh_p80 * 100).toFixed(0)}%)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">高潮判定标准</span>
        <span class="stat-val">涨停数 > P80(${mk.thresholds.zt_p80})</span>
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
        <span class="stat-val ${rs.avg_3d > 0 ? 'green' : 'red'}">${rs.avg_3d > 0 ? '+' : ''}${rs.avg_3d}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">5日平均涨停变化</span>
        <span class="stat-val ${rs.avg_5d > 0 ? 'green' : 'red'}">${rs.avg_5d > 0 ? '+' : ''}${rs.avg_5d}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">高潮总天数</span>
        <span class="stat-val yellow">${mk.gao_days.length}</span>
      </div>
    `;
    document.getElementById('reversal-stats').innerHTML = revHtml;

    chartBingGao(this.data);
    chartYearly(this.data);
    chartEchelon(this.data);
  },

  // ========== Tab: Backtest ==========
  renderBacktest() {
    const bt = this.data.backtest;
    if (!bt) {
      document.getElementById('bt-kpi').innerHTML = 
        '<div class="kpi-card"><div class="kpi-label">回测数据</div><div class="kpi-value" style="font-size:14px">暂无</div></div>';
      return;
    }

    const st = bt.stats;
    const kpiHtml = `
      <div class="kpi-card ${st.total_return >= 0 ? 'good' : 'alert'}">
        <div class="kpi-label">总收益率</div>
        <div class="kpi-value">${st.total_return > 0 ? '+' : ''}${st.total_return}%</div>
        <div class="kpi-sub">${st.days}个交易日</div>
      </div>
      <div class="kpi-card alert">
        <div class="kpi-label">最大回撤</div>
        <div class="kpi-value">${st.max_drawdown}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">初始资金</div>
        <div class="kpi-value">¥${st.initial_capital.toLocaleString()}</div>
      </div>
      <div class="kpi-card good">
        <div class="kpi-label">最终净值</div>
        <div class="kpi-value">¥${st.final_equity.toLocaleString()}</div>
      </div>
    `;
    document.getElementById('bt-kpi').innerHTML = kpiHtml;

    chartEquity(this.data);
    chartDrawdown(this.data);
    chartRegime(this.data);
  },

  // ========== Tab: Trades ==========
  renderTrades() {
    const tr = this.data.trades;
    if (!tr) {
      document.getElementById('trade-body').innerHTML = 
        '<tr><td colspan="20" style="text-align:center;padding:40px;color:#6b7585">暂无交易数据</td></tr>';
      return;
    }

    // 表头
    const headerHtml = tr.columns.map(c => `<th data-col="${c}">${c}</th>`).join('');
    document.getElementById('trade-header').innerHTML = headerHtml;

    this._trades = tr;
    this._filteredTrades = tr.rows.map((r, i) => ({ row: r, idx: i }));
    this.renderTradeRows();

    // 搜索
    document.getElementById('trade-search').addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      this._filteredTrades = tr.rows
        .map((r, i) => ({ row: r, idx: i }))
        .filter(({ row }) => row.some(v => String(v).toLowerCase().includes(q)));
      this.renderTradeRows();
    });

    // 排序
    document.querySelectorAll('[data-sort]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-sort]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const sortKey = btn.dataset.sort;
        const colIdx = tr.columns.indexOf(sortKey);
        if (colIdx >= 0) {
          const isDateCol = sortKey === 'date';
          this._filteredTrades.sort((a, b) => {
            const va = a.row[colIdx], vb = b.row[colIdx];
            if (isDateCol) {
              // 日期列按字符串比较, parseFloat 会把 '2026-02-26' 截成年份
              return String(vb).localeCompare(String(va));
            }
            const na = parseFloat(va), nb = parseFloat(vb);
            const ea = isNaN(na), eb = isNaN(nb);
            if (ea && eb) return 0;
            if (ea) return 1;   // 无效值排末尾
            if (eb) return -1;
            return nb - na;     // 降序
          });
          this.renderTradeRows();
        }
      });
    });
  },

  renderTradeRows() {
    const cols = this._trades.columns;
    const rows = this._filteredTrades;
    const html = rows.map(({ row }) => {
      const cells = row.map((v, i) => {
        const col = cols[i];
        let cls = '';
        if (col === 'action') {
          cls = v === 'BUY' ? 'buy' : 'sell';
        } else if (col === 'pnl' && v !== null && v !== '') {
          const num = parseFloat(v);
          cls = num > 0 ? 'profit' : 'loss';
        }
        const display = v === null || v === undefined ? '' : 
                        (typeof v === 'number' ? v.toFixed(2) : String(v));
        return `<td class="${cls}">${display}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
    document.getElementById('trade-body').innerHTML = html || 
      '<tr><td colspan="20" style="text-align:center;padding:20px;color:#6b7585">无匹配记录</td></tr>';
  },

  // ========== Tab: Walk-Forward ==========
  renderWalkforward() {
    const wf = this.data.walkforward;
    if (!wf) return;

    chartWalkforward(this.data);

    // 表格
    const cols = ['seg', 'start', 'end', 'ret_pct', 'max_dd_pct', 'sharpe', 'win_rate', 'n_trades'];
    const labels = ['段', '开始', '结束', '收益%', '最大回撤%', '夏普', '胜率%', '交易数'];
    
    let html = '<table><thead><tr>';
    labels.forEach(l => html += `<th>${l}</th>`);
    html += '</tr></thead><tbody>';
    
    wf.forEach(s => {
      html += '<tr>';
      cols.forEach(c => {
        let v = s[c];
        let cls = '';
        if (c === 'ret_pct') cls = v >= 0 ? 'profit' : 'loss';
        if (c === 'max_dd_pct') cls = 'loss';
        html += `<td class="${cls}">${v}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    
    document.getElementById('wf-table-wrap').innerHTML = html;
  },
};

// === 启动 ===
document.addEventListener('DOMContentLoaded', () => App.init());
