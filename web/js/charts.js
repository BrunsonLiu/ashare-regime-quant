/* ============================================
   图表渲染引擎 · Plotly 深色金融终端主题
   ============================================ */

const C = {
  bg: 'rgba(0,0,0,0)',
  paper: 'rgba(0,0,0,0)',
  text: '#d1d9e0',
  grid: '#1a2332',
  axis: '#2a3441',
  accent: '#4fd1c5',
  green: '#3ee07e',
  red: '#ff5c5c',
  yellow: '#ffb74d',
  blue: '#5b9cf5',
  purple: '#b794f4',
  orange: '#ff8c42',
  font: 'JetBrains Mono, monospace',
  fontSans: 'Noto Sans SC, sans-serif',
};

const LAYOUT = {
  paper_bgcolor: C.paper,
  plot_bgcolor: C.plot,
  font: { family: C.font, size: 10, color: C.text },
  margin: { l: 50, r: 16, t: 10, b: 32 },
  xaxis: { gridcolor: C.grid, zerolinecolor: C.axis, tickfont: { size: 9 } },
  yaxis: { gridcolor: C.grid, zerolinecolor: C.axis, tickfont: { size: 9 } },
  hoverlabel: { bgcolor: '#1a2332', bordercolor: C.axis, font: { color: C.text, size: 11 } },
  showlegend: true,
  legend: { x: 0, y: 1.12, orientation: 'h', font: { size: 10 }, bgcolor: 'rgba(0,0,0,0)' },
  colorway: [C.accent, C.yellow, C.blue, C.green, C.red, C.purple],
};

function makePlot(divId, data, extraLayout = {}, config = {}) {
  const el = document.getElementById(divId);
  if (!el) return;
  Plotly.react(divId, data, { ...LAYOUT, ...extraLayout }, {
    responsive: true,
    displayModeBar: false,
    ...config,
  });
}

// =====================
// 1. 涨停 vs 炸板率
// =====================
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
  const lh = s.lianban_height.slice(start);
  
  const traces = [
    {
      x: dates, y: zt, type: 'scatter', mode: 'lines', name: '涨停数',
      line: { color: C.accent, width: 1.5 },
      fill: 'tozeroy', fillcolor: 'rgba(79,209,197,0.06)',
      hovertemplate: '<b>%{x}</b><br>涨停: %{y} 家<extra></extra>',
    },
    {
      x: dates, y: zr.map(x => x * 100), type: 'scatter', mode: 'lines', name: '炸板率%',
      line: { color: C.red, width: 1, dash: 'dot' },
      yaxis: 'y2',
      hovertemplate: '炸板率: %{y:.1f}%<extra></extra>',
    },
    {
      x: dates, y: lh, type: 'scatter', mode: 'lines', name: '连板高度',
      line: { color: C.yellow, width: 1, dash: 'dash' },
      yaxis: 'y3',
      hovertemplate: '连板高度: %{y}<extra></extra>',
    },
  ];
  
  // P20 / P80 参考线
  if (s.quantiles) {
    traces.push({
      x: [dates[0], dates[dates.length-1]],
      y: [s.quantiles.zt_count.p20, s.quantiles.zt_count.p20],
      type: 'scatter', mode: 'lines', name: 'P20 冰点线',
      line: { color: C.blue, width: 1, dash: 'dashdot' },
      hoverinfo: 'skip',
    });
    traces.push({
      x: [dates[0], dates[dates.length-1]],
      y: [s.quantiles.zt_count.p80, s.quantiles.zt_count.p80],
      type: 'scatter', mode: 'lines', name: 'P80 高潮线',
      line: { color: C.orange, width: 1, dash: 'dashdot' },
      hoverinfo: 'skip',
    });
  }
  
  makePlot('chart-zt-zhaban', traces, {
    yaxis: { title: '涨停数', gridcolor: C.grid, tickfont: { size: 9 } },
    yaxis2: { title: '炸板率%', overlaying: 'y', side: 'right', gridcolor: 'rgba(0,0,0,0)', tickfont: { size: 9 }, tickformat: '.0f' },
    yaxis3: { title: '连板', overlaying: 'y', side: 'right', anchor: 'free', autoshift: true, tickfont: { size: 9 } },
    height: 340,
  });
}

// =====================
// 2. 连板高度分布
// =====================
function chartLianban(data) {
  const s = data.sentiment;
  if (!s) return;
  
  const last60 = Math.min(60, s.dates.length);
  const start = s.dates.length - last60;
  
  const traces = [
    { x: s.dates.slice(start), y: s.lianban2.slice(start), type: 'bar', name: '2板', marker: { color: C.accent }, },
    { x: s.dates.slice(start), y: s.lianban3.slice(start), type: 'bar', name: '3板', marker: { color: C.yellow }, },
    { x: s.dates.slice(start), y: s.lianban4p.slice(start), type: 'bar', name: '4板+', marker: { color: C.red }, },
  ];
  
  makePlot('chart-lianban', traces, {
    barmode: 'stack',
    height: 340,
    legend: { x: 0, y: 1.15, orientation: 'h' },
    yaxis: { title: '家数', gridcolor: C.grid },
  });
}

// =====================
// 3. 首板占比
// =====================
function chartShouban(data) {
  const s = data.sentiment;
  if (!s) return;
  
  const last120 = Math.min(120, s.dates.length);
  const start = s.dates.length - last120;
  
  const ratio = s.shouban_ratio.slice(start);
  const dates = s.dates.slice(start);
  
  const trace = {
    x: dates, y: ratio.map(x => x * 100),
    type: 'scatter', mode: 'lines', fill: 'tozeroy',
    line: { color: C.purple, width: 1.5 },
    fillcolor: 'rgba(183,148,244,0.1)',
    hovertemplate: '<b>%{x}</b><br>首板占比: %{y:.1f}%<extra></extra>',
  };
  
  makePlot('chart-shouban', [trace], {
    yaxis: { title: '占比%', gridcolor: C.grid, tickformat: '.0f' },
    height: 340,
  });
}

// =====================
// 4. 月度热力图
// =====================
function chartMonthlyHeat(data) {
  const m = data.monthly;
  if (!m) return;
  
  // 转成热力图格式: rows=年, cols=月
  const years = [...new Set(m.months.map(x => x.substring(0, 4)))].sort();
  const months = ['01','02','03','04','05','06','07','08','09','10','11','12'];
  
  const z = years.map(y => months.map(mon => {
    const ym = `${y}-${mon}`;
    const idx = m.months.indexOf(ym);
    return idx >= 0 ? m.zt_mean[idx] : null;
  }));
  
  const trace = {
    z, x: months.map(x => x + '月'), y: years,
    type: 'heatmap',
    colorscale: [[0, '#1a2332'], [0.3, C.blue], [0.6, C.accent], [1, C.red]],
    showscale: true,
    hovertemplate: '%{y}年 %{x}<br>日均涨停: %{z:.1f} 家<extra></extra>',
    xgap: 2, ygap: 2,
  };
  
  makePlot('chart-monthly-heat', [trace], {
    height: 340,
    margin: { l: 50, r: 16, t: 10, b: 32 },
    yaxis: { gridcolor: 'rgba(0,0,0,0)', tickfont: { size: 11 } },
    xaxis: { gridcolor: 'rgba(0,0,0,0)', tickfont: { size: 9 } },
  });
}

// =====================
// 5. 冰点/高潮标记
// =====================
function chartBingGao(data) {
  const s = data.sentiment;
  const mk = data.markers;
  if (!s || !mk) return;
  
  const last250 = Math.min(250, s.dates.length);
  const start = s.dates.length - last250;
  
  const dates = s.dates.slice(start);
  const zt = s.zt_count.slice(start);
  
  // 涨停数主线
  const traces = [{
    x: dates, y: zt, type: 'scatter', mode: 'lines', name: '涨停数',
    line: { color: C.accent, width: 1.5 },
    hovertemplate: '<b>%{x}</b><br>涨停: %{y}<extra></extra>',
  }];
  
  // 冰点标记
  const bingDates = mk.bing_days.filter(d => dates.includes(d));
  const bingVals = bingDates.map(d => {
    const i = dates.indexOf(d);
    return i >= 0 ? zt[i] : null;
  });
  if (bingDates.length) {
    traces.push({
      x: bingDates, y: bingVals, type: 'scatter', mode: 'markers',
      name: '冰点', marker: { color: C.blue, size: 8, symbol: 'circle-open', line: { width: 2 } },
      hovertemplate: '🧊 冰点<br>%{x}<br>涨停: %{y}<extra></extra>',
    });
  }
  
  // 高潮标记
  const gaoDates = mk.gao_days.filter(d => dates.includes(d));
  const gaoVals = gaoDates.map(d => {
    const i = dates.indexOf(d);
    return i >= 0 ? zt[i] : null;
  });
  if (gaoDates.length) {
    traces.push({
      x: gaoDates, y: gaoVals, type: 'scatter', mode: 'markers',
      name: '高潮', marker: { color: C.red, size: 8, symbol: 'circle-open', line: { width: 2 } },
      hovertemplate: '🔥 高潮<br>%{x}<br>涨停: %{y}<extra></extra>',
    });
  }
  
  // 参考线
  if (mk.thresholds) {
    traces.push({
      x: [dates[0], dates[dates.length-1]], y: [mk.thresholds.zt_p20, mk.thresholds.zt_p20],
      type: 'scatter', mode: 'lines', name: `P20=${mk.thresholds.zt_p20}`,
      line: { color: C.blue, width: 1, dash: 'dashdot' }, hoverinfo: 'skip',
    });
    traces.push({
      x: [dates[0], dates[dates.length-1]], y: [mk.thresholds.zt_p80, mk.thresholds.zt_p80],
      type: 'scatter', mode: 'lines', name: `P80=${mk.thresholds.zt_p80}`,
      line: { color: C.orange, width: 1, dash: 'dashdot' }, hoverinfo: 'skip',
    });
  }
  
  makePlot('chart-bing-gao', traces, { height: 340 });
}

// =====================
// 6. 年度对比
// =====================
function chartYearly(data) {
  const y = data.yearly;
  if (!y) return;
  
  const traces = [
    {
      x: y.map(x => x.year), y: y.map(x => x.zt_mean),
      type: 'bar', name: '日均涨停', marker: { color: C.accent },
      hovertemplate: '%{x}年<br>日均涨停: %{y:.1f}<extra></extra>',
    },
    {
      x: y.map(x => x.year), y: y.map(x => x.bing_days),
      type: 'bar', name: '冰点天数', marker: { color: C.blue },
      hovertemplate: '%{x}年<br>冰点天数: %{y}<extra></extra>',
    },
  ];
  
  makePlot('chart-yearly', traces, {
    barmode: 'group',
    height: 340,
    yaxis: { title: '数量', gridcolor: C.grid },
  });
}

// =====================
// 7. 连板梯队
// =====================
function chartEchelon(data) {
  const s = data.sentiment;
  if (!s) return;
  
  const last60 = Math.min(60, s.dates.length);
  const start = s.dates.length - last60;
  
  const dates = s.dates.slice(start);
  
  const traces = [
    { x: dates, y: s.shouban.slice(start), type: 'bar', name: '首板', marker: { color: C.accent } },
    { x: dates, y: s.lianban2.slice(start), type: 'bar', name: '2板', marker: { color: C.yellow } },
    { x: dates, y: s.lianban3.slice(start), type: 'bar', name: '3板', marker: { color: C.orange } },
    { x: dates, y: s.lianban4p.slice(start), type: 'bar', name: '4板+', marker: { color: C.red } },
  ];
  
  makePlot('chart-echelon', traces, {
    barmode: 'stack',
    height: 340,
    yaxis: { title: '家数', gridcolor: C.grid },
    legend: { x: 0, y: 1.15, orientation: 'h' },
  });
}

// =====================
// 8. 净值曲线
// =====================
function chartEquity(data) {
  const bt = data.backtest;
  if (!bt) { document.getElementById('chart-equity').innerHTML = '<div class="empty-state">暂无回测数据</div>'; return; }
  
  const traces = [{
    x: bt.dates, y: bt.equity,
    type: 'scatter', mode: 'lines', name: '净值',
    line: { color: C.accent, width: 2 },
    fill: 'tozeroy', fillcolor: 'rgba(79,209,197,0.06)',
    hovertemplate: '<b>%{x}</b><br>净值: ¥%{y:,.0f}<extra></extra>',
  }];
  
  makePlot('chart-equity', traces, {
    height: 340,
    yaxis: { title: '净值 (¥)', gridcolor: C.grid, tickformat: ',.0f' },
  });
}

// =====================
// 9. 回撤曲线
// =====================
function chartDrawdown(data) {
  const bt = data.backtest;
  if (!bt) return;
  
  const traces = [{
    x: bt.dates, y: bt.drawdown,
    type: 'scatter', mode: 'lines', name: '回撤%',
    line: { color: C.red, width: 1.5 },
    fill: 'tozeroy', fillcolor: 'rgba(255,92,92,0.1)',
    hovertemplate: '<b>%{x}</b><br>回撤: %{y:.2f}%<extra></extra>',
  }];
  
  makePlot('chart-drawdown', [trace], {
    height: 340,
    yaxis: { title: '回撤%', gridcolor: C.grid, tickformat: '.1f' },
  });
}

// =====================
// 10. 市场状态
// =====================
function chartRegime(data) {
  const bt = data.backtest;
  if (!bt || !bt.regime) return;
  
  // 转成色带
  const regimeColor = { BULL: C.green, SHOCK: C.yellow, BEAR: C.red, UNKNOWN: '#2a3441' };
  
  const segments = [];
  let prevRegime = bt.regime[0];
  let startIdx = 0;
  
  for (let i = 1; i < bt.regime.length; i++) {
    if (bt.regime[i] !== prevRegime) {
      segments.push({ start: bt.dates[startIdx], end: bt.dates[i-1], regime: prevRegime });
      startIdx = i;
      prevRegime = bt.regime[i];
    }
  }
  segments.push({ start: bt.dates[startIdx], end: bt.dates[bt.dates.length-1], regime: prevRegime });
  
  const traces = segments.map(seg => ({
    x: [seg.start, seg.end], y: [1, 1],
    type: 'scatter', mode: 'lines',
    name: seg.regime,
    line: { color: regimeColor[seg.regime] || C.text, width: 12 },
    hovertemplate: `${seg.regime}<br>${seg.start} ~ ${seg.end}<extra></extra>`,
  }));
  
  makePlot('chart-regime', traces, {
    height: 200,
    yaxis: { showgrid: false, showticklabels: false, zeroline: false },
    xaxis: { gridcolor: C.grid },
    showlegend: true,
    legend: { x: 0, y: 1.3, orientation: 'h' },
  });
}

// =====================
// 11. Walk-Forward
// =====================
function chartWalkforward(data) {
  const wf = data.walkforward;
  if (!wf) return;
  
  const traces = [
    {
      x: wf.map(x => `Seg${x.seg}`), y: wf.map(x => x.ret_pct),
      type: 'bar', name: '收益率%',
      marker: { color: wf.map(x => x.ret_pct >= 0 ? C.green : C.red) },
      hovertemplate: 'Seg%{x}<br>收益: %{y:.2f}%<extra></extra>',
    },
    {
      x: wf.map(x => `Seg${x.seg}`), y: wf.map(x => x.max_dd_pct),
      type: 'scatter', mode: 'lines+markers', name: '最大回撤%',
      line: { color: C.red, width: 1.5, dash: 'dash' },
      hovertemplate: '最大回撤: %{y:.2f}%<extra></extra>',
    },
    {
      x: wf.map(x => `Seg${x.seg}`), y: wf.map(x => x.sharpe),
      type: 'scatter', mode: 'lines+markers', name: '夏普',
      line: { color: C.accent, width: 1.5 },
      yaxis: 'y2',
      hovertemplate: '夏普: %{y:.2f}<extra></extra>',
    },
  ];
  
  makePlot('chart-wf', traces, {
    height: 340,
    barmode: 'group',
    yaxis: { title: '%', gridcolor: C.grid },
    yaxis2: { title: '夏普', overlaying: 'y', side: 'right', gridcolor: 'rgba(0,0,0,0)' },
  });
}
