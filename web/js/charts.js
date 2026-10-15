/* ============================================
   情绪终端图表 · 依赖 shared.js 提供的 C / LAYOUT / makePlot
   (配色与基座统一在 shared.js 定义, 本文件不再重复声明)
   ============================================ */

/* ============================================
   1. 涨停家数 + 炸板率(双轴, 不再叠加第三条线)
   ============================================ */
function chartZtZhaban(data, range = 'all') {
  const s = data.sentiment;
  if (!s) return;

  let n = s.dates.length;
  if (range === '1y') n = Math.min(n, 250);
  if (range === '3m') n = Math.min(n, 60);
  const start = s.dates.length - n;

  const dates = s.dates.slice(start);
  const zt = s.zt_count.slice(start);
  const zr = s.zhaban_rate.slice(start);

  const traces = [
    {
      x: dates, y: zt, type: 'scatter', mode: 'lines', name: '涨停数',
      line: { color: C.accent, width: 1.5 },
      fill: 'tozeroy', fillcolor: C.fillBlue,
      hovertemplate: '<b>%{x}</b><br>涨停 %{y} 家<extra></extra>',
    },
    {
      x: dates, y: zr.map(x => x * 100), type: 'scatter', mode: 'lines',
      name: '炸板率%', line: { color: C.up, width: 1, dash: 'dot' },
      yaxis: 'y2',
      hovertemplate: '炸板率 %{y:.1f}%<extra></extra>',
    },
  ];

  if (s.quantiles) {
    traces.push({
      x: [dates[0], dates[dates.length - 1]],
      y: [s.quantiles.zt_count.p20, s.quantiles.zt_count.p20],
      type: 'scatter', mode: 'lines', name: 'P20 冰点线',
      line: { color: C.blue, width: 1, dash: 'dashdot' },
      hoverinfo: 'skip',
    });
    traces.push({
      x: [dates[0], dates[dates.length - 1]],
      y: [s.quantiles.zt_count.p80, s.quantiles.zt_count.p80],
      type: 'scatter', mode: 'lines', name: 'P80 高潮线',
      line: { color: C.orange, width: 1, dash: 'dashdot' },
      hoverinfo: 'skip',
    });
  }

  makePlot('chart-zt-zhaban', traces, {
    height: CHART_H_TALL,
    yaxis: { title: '涨停数', gridcolor: C.grid, tickfont: { size: 9 } },
    yaxis2: {
      title: '炸板率%', overlaying: 'y', side: 'right',
      gridcolor: 'rgba(0,0,0,0)', tickfont: { size: 9 }, tickformat: '.0f',
    },
    margin: { l: 52, r: 48, t: 12, b: 34 },
  });
}

/* ============================================
   2. 连板高度走势(从原双轴图里独立出来)
   ============================================ */
function chartLianbanHeight(data) {
  const s = data.sentiment;
  if (!s) return;

  const n = Math.min(250, s.dates.length);
  const start = s.dates.length - n;
  const dates = s.dates.slice(start);
  const lh = s.lianban_height.slice(start);

  const traces = [{
    x: dates, y: lh, type: 'scatter', mode: 'lines', name: '最高连板',
    line: { color: C.yellow, width: 1.5 },
    fill: 'tozeroy', fillcolor: C.fillBlue,
    hovertemplate: '<b>%{x}</b><br>最高连板 %{y} 板<extra></extra>',
  }];

  if (s.quantiles && s.quantiles.lianban_height) {
    traces.push({
      x: [dates[0], dates[dates.length - 1]],
      y: [s.quantiles.lianban_height.p90, s.quantiles.lianban_height.p90],
      type: 'scatter', mode: 'lines', name: `P90 (${s.quantiles.lianban_height.p90})`,
      line: { color: C.orange, width: 1, dash: 'dashdot' },
      hoverinfo: 'skip',
    });
  }

  makePlot('chart-lianban-height', traces, {
    height: CHART_H,
    yaxis: { title: '板数', gridcolor: C.grid, tickfont: { size: 9 } },
  });
}

/* ============================================
   3. 连板梯队结构
   ============================================ */
function chartLianban(data) {
  const s = data.sentiment;
  if (!s) return;

  const last60 = Math.min(60, s.dates.length);
  const start = s.dates.length - last60;

  const traces = [
    { x: s.dates.slice(start), y: s.lianban2.slice(start), type: 'bar', name: '2板', marker: { color: C.accent } },
    { x: s.dates.slice(start), y: s.lianban3.slice(start), type: 'bar', name: '3板', marker: { color: C.yellow } },
    { x: s.dates.slice(start), y: s.lianban4p.slice(start), type: 'bar', name: '4板+', marker: { color: C.red } },
  ];

  makePlot('chart-lianban', traces, {
    barmode: 'stack',
    height: CHART_H,
    yaxis: { title: '家数', gridcolor: C.grid, tickfont: { size: 9 } },
  });
}

/* ============================================
   4. 首板占比
   ============================================ */
function chartShouban(data) {
  const s = data.sentiment;
  if (!s) return;

  const n = Math.min(120, s.dates.length);
  const start = s.dates.length - n;
  const dates = s.dates.slice(start);
  const ratio = s.shouban_ratio.slice(start);

  const trace = {
    x: dates, y: ratio.map(x => x * 100),
    type: 'scatter', mode: 'lines', name: '首板占比',
    line: { color: C.purple, width: 1.5 },
    fill: 'tozeroy', fillcolor: 'rgba(107,79,184,0.08)',
    hovertemplate: '<b>%{x}</b><br>首板占比 %{y:.1f}%<extra></extra>',
  };

  makePlot('chart-shouban', [trace], {
    height: CHART_H,
    yaxis: { title: '占比%', gridcolor: C.grid, tickformat: '.0f', tickfont: { size: 9 } },
  });
}

/* ============================================
   5. 月度热力图
   ============================================ */
function chartMonthlyHeat(data) {
  const m = data.monthly;
  if (!m) return;

  const years = [...new Set(m.months.map(x => x.substring(0, 4)))].sort();
  const months = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'];

  const z = years.map(y => months.map(mon => {
    const idx = m.months.indexOf(`${y}-${mon}`);
    return idx >= 0 ? m.zt_mean[idx] : null;
  }));

  const trace = {
    z, x: months.map(x => x + '月'), y: years,
    type: 'heatmap',
    colorscale: [[0, '#f3f5f7'], [0.3, C.blue], [0.6, C.accent], [1, C.red]],
    showscale: true,
    hovertemplate: '%{y}年 %{x}<br>日均涨停 %{z:.1f} 家<extra></extra>',
    xgap: 2, ygap: 2,
  };

  makePlot('chart-monthly-heat', [trace], {
    height: CHART_H,
    yaxis: { gridcolor: 'rgba(0,0,0,0)', tickfont: { size: 11 } },
    xaxis: { gridcolor: 'rgba(0,0,0,0)', tickfont: { size: 9 } },
  });
}

/* ============================================
   6. 冰点 / 高潮标记
   ============================================ */
function chartBingGao(data) {
  const s = data.sentiment;
  const mk = data.markers;
  if (!s || !mk) return;

  const n = Math.min(250, s.dates.length);
  const start = s.dates.length - n;
  const dates = s.dates.slice(start);
  const zt = s.zt_count.slice(start);

  const traces = [{
    x: dates, y: zt, type: 'scatter', mode: 'lines', name: '涨停数',
    line: { color: C.accent, width: 1.5 },
    fill: 'tozeroy', fillcolor: C.fillBlue,
    hovertemplate: '<b>%{x}</b><br>涨停 %{y}<extra></extra>',
  }];

  const markDays = (days, name, color) => {
    const hit = (days || []).filter(d => dates.includes(d));
    if (!hit.length) return;
    traces.push({
      x: hit, y: hit.map(d => zt[dates.indexOf(d)]),
      type: 'scatter', mode: 'markers', name,
      marker: { color, size: 8, symbol: 'circle-open', line: { width: 2 } },
      hovertemplate: `${name}<br>%{x}<br>涨停 %{y}<extra></extra>`,
    });
  };
  markDays(mk.bing_days, '冰点', C.blue);
  markDays(mk.gao_days, '高潮', C.red);

  if (mk.thresholds) {
    traces.push({
      x: [dates[0], dates[dates.length - 1]], y: [mk.thresholds.zt_p20, mk.thresholds.zt_p20],
      type: 'scatter', mode: 'lines', name: `P20 (${mk.thresholds.zt_p20})`,
      line: { color: C.blue, width: 1, dash: 'dashdot' }, hoverinfo: 'skip',
    });
    traces.push({
      x: [dates[0], dates[dates.length - 1]], y: [mk.thresholds.zt_p80, mk.thresholds.zt_p80],
      type: 'scatter', mode: 'lines', name: `P80 (${mk.thresholds.zt_p80})`,
      line: { color: C.orange, width: 1, dash: 'dashdot' }, hoverinfo: 'skip',
    });
  }

  makePlot('chart-bing-gao', traces, { height: CHART_H_TALL });
}

/* ============================================
   7. 年度对比
   ============================================ */
function chartYearly(data) {
  const y = data.yearly;
  if (!y) return;

  const traces = [
    {
      x: y.map(x => x.year), y: y.map(x => x.zt_mean),
      type: 'bar', name: '日均涨停', marker: { color: C.accent },
      hovertemplate: '%{x}年<br>日均涨停 %{y:.1f}<extra></extra>',
    },
    {
      x: y.map(x => x.year), y: y.map(x => x.bing_days),
      type: 'bar', name: '冰点天数', marker: { color: C.blue },
      hovertemplate: '%{x}年<br>冰点 %{y} 天<extra></extra>',
    },
  ];

  makePlot('chart-yearly', traces, {
    barmode: 'group',
    height: CHART_H,
    yaxis: { title: '数量', gridcolor: C.grid, tickfont: { size: 9 } },
  });
}

/* ============================================
   8. 连板梯队 (近60日, 含首板)
   ============================================ */
function chartEchelon(data) {
  const s = data.sentiment;
  if (!s) return;

  const n = Math.min(60, s.dates.length);
  const start = s.dates.length - n;
  const dates = s.dates.slice(start);

  const traces = [
    { x: dates, y: s.shouban.slice(start), type: 'bar', name: '首板', marker: { color: C.accent } },
    { x: dates, y: s.lianban2.slice(start), type: 'bar', name: '2板', marker: { color: C.yellow } },
    { x: dates, y: s.lianban3.slice(start), type: 'bar', name: '3板', marker: { color: C.orange } },
    { x: dates, y: s.lianban4p.slice(start), type: 'bar', name: '4板+', marker: { color: C.red } },
  ];

  makePlot('chart-echelon', traces, {
    barmode: 'stack',
    height: CHART_H,
    yaxis: { title: '家数', gridcolor: C.grid, tickfont: { size: 9 } },
  });
}

/* ============================================
   9. 净值曲线
   ============================================ */
function chartEquity(data) {
  const bt = data.backtest;
  if (!bt) { renderEmpty('chart-equity', '暂无回测数据'); return; }

  const traces = [{
    x: bt.dates, y: bt.equity,
    type: 'scatter', mode: 'lines', name: '净值',
    line: { color: C.accent, width: 2 },
    fill: 'tozeroy', fillcolor: C.fillBlue,
    hovertemplate: '<b>%{x}</b><br>净值 ¥%{y:,.0f}<extra></extra>',
  }];

  makePlot('chart-equity', traces, {
    height: CHART_H_TALL,
    yaxis: { title: '净值 (¥)', gridcolor: C.grid, tickformat: ',.0f', tickfont: { size: 9 } },
  });
}

/* ============================================
   10. 回撤曲线
   ============================================ */
function chartDrawdown(data) {
  const bt = data.backtest;
  if (!bt) { renderEmpty('chart-drawdown', '暂无回测数据'); return; }

  const traces = [{
    x: bt.dates, y: bt.drawdown,
    type: 'scatter', mode: 'lines', name: '回撤%',
    line: { color: C.red, width: 1.5 },
    fill: 'tozeroy', fillcolor: C.fillRed,
    hovertemplate: '<b>%{x}</b><br>回撤 %{y:.2f}%<extra></extra>',
  }];

  makePlot('chart-drawdown', traces, {
    height: CHART_H,
    yaxis: { title: '回撤%', gridcolor: C.grid, tickformat: '.1f', tickfont: { size: 9 } },
  });
}

/* ============================================
   11. 市场状态色带
   ============================================ */
function chartRegime(data) {
  const bt = data.backtest;
  if (!bt || !bt.regime) { renderEmpty('chart-regime', '暂无状态数据'); return; }

  const regimeColor = { BULL: C.up, SHOCK: C.yellow, BEAR: C.down, UNKNOWN: '#c8ccd2' };

  const segments = [];
  let prev = bt.regime[0];
  let startIdx = 0;
  for (let i = 1; i < bt.regime.length; i++) {
    if (bt.regime[i] !== prev) {
      segments.push({ start: bt.dates[startIdx], end: bt.dates[i - 1], regime: prev });
      startIdx = i;
      prev = bt.regime[i];
    }
  }
  segments.push({ start: bt.dates[startIdx], end: bt.dates[bt.dates.length - 1], regime: prev });

  makePlot('chart-regime', segments.map(seg => ({
    x: [seg.start, seg.end], y: [1, 1],
    type: 'scatter', mode: 'lines', name: seg.regime,
    line: { color: regimeColor[seg.regime] || C.text, width: 12 },
    hovertemplate: `${seg.regime}<br>${seg.start} ~ ${seg.end}<extra></extra>`,
  })), {
    height: CHART_H_SHORT,
    margin: { l: 20, r: 20, t: 12, b: 34 },
    yaxis: { showgrid: false, showticklabels: false, zeroline: false },
    xaxis: { gridcolor: C.grid },
    showlegend: true,
    legend: { x: 0, y: 1.35, orientation: 'h' },
  });
}

/* ============================================
   12. Walk-Forward
   ============================================ */
function chartWalkforward(data) {
  const wf = data.walkforward;
  if (!wf) { renderEmpty('chart-wf', '暂无滚动验证数据'); return; }

  const labels = wf.map(x => `Seg${x.seg}`);

  const traces = [
    {
      x: labels, y: wf.map(x => x.ret_pct),
      type: 'bar', name: '收益率%',
      marker: { color: wf.map(x => x.ret_pct >= 0 ? C.up : C.down) },
      hovertemplate: '%{x}<br>收益 %{y:.2f}%<extra></extra>',
    },
    {
      x: labels, y: wf.map(x => x.max_dd_pct),
      type: 'scatter', mode: 'lines+markers', name: '最大回撤%',
      line: { color: C.red, width: 1.5, dash: 'dash' },
      hovertemplate: '最大回撤 %{y:.2f}%<extra></extra>',
    },
    {
      x: labels, y: wf.map(x => x.sharpe),
      type: 'scatter', mode: 'lines+markers', name: '夏普',
      line: { color: C.accent, width: 1.5 }, marker: { size: 6 },
      yaxis: 'y2',
      hovertemplate: '夏普 %{y:.2f}<extra></extra>',
    },
  ];

  makePlot('chart-wf', traces, {
    height: CHART_H_TALL,
    barmode: 'group',
    yaxis: { title: '%', gridcolor: C.grid, tickfont: { size: 9 } },
    yaxis2: { title: '夏普', overlaying: 'y', side: 'right', gridcolor: 'rgba(0,0,0,0)', tickfont: { size: 9 } },
    margin: { l: 52, r: 48, t: 12, b: 34 },
  });
}