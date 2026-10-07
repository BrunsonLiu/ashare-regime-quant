/* ============================================
   共享工具库 · 导航 + 数据加载 + 通用函数
   ============================================ */

const NAV_CONFIG = [
  {
    section: '核心',
    items: [
      { icon: '◈', label: '情绪终端', href: 'index.html', key: 'sentiment' },
      { icon: '☀', label: '每日决策', href: 'daily.html', key: 'daily' },
      { icon: '◎', label: '市场状态', href: 'regime.html', key: 'regime' },
      { icon: '◉', label: '实时概览', href: 'live.html', key: 'live' },
    ]
  },
  {
    section: '分析',
    items: [
      { icon: '◇', label: '外围市场', href: 'overseas.html', key: 'overseas' },
      { icon: '◆', label: '交易信号', href: 'signals.html', key: 'signals' },
      { icon: '▦', label: '因子分析', href: 'factors.html', key: 'factors' },
    ]
  },
  {
    section: '体系',
    items: [
      { icon: '☆', label: '毛选原则', href: 'principles.html', key: 'principles' },
      { icon: '▤', label: '回测绩效', href: 'index.html#tab-backtest', key: 'backtest' },
    ]
  },
];

const C = {
  bg: 'rgba(0,0,0,0)',
  paper: 'rgba(0,0,0,0)',
  plot: 'rgba(0,0,0,0)',
  text: '#c9cdd4',
  grid: '#2a2e36',
  axis: '#383d47',
  accent: '#5b8def',
  /* A股约定: 红涨绿跌 */
  up: '#d9524f',
  down: '#35a06b',
  green: '#35a06b',
  red: '#d9524f',
  yellow: '#d9a441',
  blue: '#5b8def',
  purple: '#a48ad4',
  orange: '#d98a3d',
  font: 'SF Mono, Cascadia Mono, Consolas, monospace',
  fontSans: '-apple-system, PingFang SC, Microsoft YaHei, sans-serif',
};

const LAYOUT = {
  paper_bgcolor: C.paper,
  plot_bgcolor: C.plot,
  font: { family: C.fontSans, size: 10, color: C.text },
  margin: { l: 50, r: 16, t: 10, b: 32 },
  xaxis: { gridcolor: C.grid, zerolinecolor: C.axis, tickfont: { size: 9 } },
  yaxis: { gridcolor: C.grid, zerolinecolor: C.axis, tickfont: { size: 9 } },
  hoverlabel: { bgcolor: '#262a31', bordercolor: C.axis, font: { color: C.text, size: 11 } },
  showlegend: true,
  legend: { x: 0, y: 1.12, orientation: 'h', font: { size: 10 }, bgcolor: 'rgba(0,0,0,0)' },
  colorway: [C.accent, C.yellow, C.blue, C.orange, C.up, C.purple],
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

// === 渲染共享布局 ===
function renderLayout(activeKey) {
  // 顶栏
  const topbar = `
    <header id="topbar">
      <div class="topbar-left">
        <span class="logo">龙头量化</span>
        <span class="version">行业龙头 · 环境择时</span>
      </div>
      <div class="topbar-center">
        <span id="clock" class="clock">--:--:--</span>
      </div>
      <div class="topbar-right">
        <span id="market-status" class="market-status">●</span>
        <span id="market-label">LOADING</span>
      </div>
    </header>
  `;
  
  // 侧边栏
  let sidebar = '<nav id="sidebar">';
  NAV_CONFIG.forEach(sec => {
    sidebar += `<div class="nav-section">`;
    sidebar += `<div class="nav-section-title">${sec.section}</div>`;
    sec.items.forEach(item => {
      const cls = item.key === activeKey ? 'nav-link active' : 'nav-link';
      sidebar += `<a class="${cls}" href="${item.href}">${item.label}</a>`;
    });
    sidebar += `</div>`;
  });
  sidebar += '</nav>';
  
  document.body.insertAdjacentHTML('afterbegin', topbar + sidebar);
  
  // 时钟
  function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = 
      `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
  }
  updateClock();
  setInterval(updateClock, 1000);
  
  // 市场状态
  function updateMarketStatus() {
    const now = new Date();
    const day = now.getDay();
    const hm = now.getHours() * 60 + now.getMinutes();
    const isOpen = day >= 1 && day <= 5 && ((hm >= 570 && hm <= 690) || (hm >= 780 && hm <= 900));
    const dot = document.getElementById('market-status');
    const label = document.getElementById('market-label');
    if (isOpen) { dot.className = 'market-status open'; label.textContent = 'OPEN'; }
    else { dot.className = 'market-status closed'; label.textContent = 'CLOSED'; }
  }
  updateMarketStatus();
  
  // Footer
  const footer = `
    <footer id="footer">
      <span>龙头量化 · 行业龙头策略系统 · <span id="data-range">--</span></span>
      <span id="last-update">--</span>
    </footer>
  `;
  document.body.insertAdjacentHTML('beforeend', footer);
  document.getElementById('last-update').textContent = `Updated: ${new Date().toLocaleString('zh-CN')}`;
}

// === 数据加载 ===
const DataLoader = {
  cache: {},
  
  async load(name) {
    if (this.cache[name]) return this.cache[name];
    try {
      const res = await fetch(`data/${name}.json`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      this.cache[name] = data;
      return data;
    } catch (e) {
      console.warn(`[DataLoader] ${name}.json:`, e.message);
      return null;
    }
  },
  
  async loadMulti(names) {
    const results = await Promise.all(names.map(n => this.load(n)));
    return Object.fromEntries(names.map((n, i) => [n, results[i]]));
  },
};

// === 工具函数 ===
function fmt(v, decimals = 2) {
  if (v === null || v === undefined || isNaN(v)) return '--';
  return typeof v === 'number' ? v.toFixed(decimals) : String(v);
}

function fmtPct(v, decimals = 2) {
  if (v === null || v === undefined || isNaN(v)) return '--';
  return `${v > 0 ? '+' : ''}${v.toFixed(decimals)}%`;
}

function fmtMoney(v) {
  if (v === null || v === undefined || isNaN(v)) return '--';
  if (Math.abs(v) >= 1e8) return `¥${(v / 1e8).toFixed(2)}亿`;
  if (Math.abs(v) >= 1e4) return `¥${(v / 1e4).toFixed(1)}万`;
  return `¥${v.toFixed(0)}`;
}

function regimeBadge(regime) {
  const cls = regime === 'BULL' ? 'bull' : regime === 'BEAR' ? 'bear' : 'shock';
  return `<span class="badge ${cls}">${regime}</span>`;
}

function showError(msg) {
  document.getElementById('main').innerHTML = 
    `<div style="text-align:center;padding:80px;color:#ff5c5c;font-family:monospace;">⚠ ${msg}</div>`;
}
