/* ============================================
   共享基础库 · 唯一真源
   导航 / 配色 / 图表基座 / 数据加载 / 工具函数

   页面统一用法:
     <script src="js/shared.js"></script>
     <script>renderLayout('pageKey');</script>
   charts.js 依赖本文件提供的 C / LAYOUT / makePlot, 不再重复定义。
   ============================================ */

/* ============================================
   1. 导航配置
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

/* ============================================
   2. 配色(与 css/shared.css 的 :root 保持一致)
   ============================================ */
const C = {
  bg: 'rgba(0,0,0,0)',
  paper: 'rgba(0,0,0,0)',
  plot: 'rgba(0,0,0,0)',
  text: '#5b6470',
  grid: '#e8eaed',
  axis: '#dcdfe3',
  accent: '#1b62c4',
  /* A股约定: 红涨绿跌 */
  up: '#c92a2a',
  down: '#067d47',
  green: '#067d47',
  red: '#c92a2a',
  yellow: '#966100',
  blue: '#1b62c4',
  purple: '#6b4fb8',
  orange: '#a85a12',
  fillRed: 'rgba(201,42,42,0.07)',
  fillGreen: 'rgba(6,125,71,0.07)',
  fillBlue: 'rgba(27,98,196,0.07)',
  font: 'SF Mono, Cascadia Mono, Consolas, monospace',
  fontSans: '-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif',
};

const CHART_H = 300;   // 与 css 的 --chart-h 一致
const CHART_H_TALL = 380;
const CHART_H_SHORT = 200;

const LAYOUT = {
  paper_bgcolor: C.paper,
  plot_bgcolor: C.plot,
  font: { family: C.fontSans, size: 10, color: C.text },
  margin: { l: 52, r: 20, t: 12, b: 34 },
  xaxis: { gridcolor: C.grid, zerolinecolor: C.axis, tickfont: { size: 9 } },
  yaxis: { gridcolor: C.grid, zerolinecolor: C.axis, tickfont: { size: 9 } },
  hoverlabel: { bgcolor: '#ffffff', bordercolor: C.axis, font: { color: '#1c2026', size: 11 } },
  showlegend: true,
  legend: { x: 0, y: 1.14, orientation: 'h', font: { size: 10 }, bgcolor: 'rgba(0,0,0,0)' },
  colorway: [C.accent, C.yellow, C.orange, C.green, C.red, C.purple],
};

let _plotlyMissing = false;

function makePlot(divId, data, extraLayout = {}, config = {}) {
  const el = document.getElementById(divId);
  if (!el) return;
  /* Plotly 走 CDN, 断网或 CDN 抽风时 window.Plotly 不存在。
     原来这里直接抛 ReferenceError, 整页脚本中断 => 白屏 */
  if (typeof window.Plotly === 'undefined') {
    el.innerHTML = `<div class="empty-state">
      <div class="empty-title">图表库未加载</div>
      <div class="empty-hint">cdn.plot.ly 不可达，检查网络后刷新</div>
    </div>`;
    if (!_plotlyMissing) {
      _plotlyMissing = true;
      const main = document.getElementById('main');
      if (main) {
        main.insertAdjacentHTML('afterbegin',
          `<div class="callout wait" style="margin:0 0 10px">
             Plotly 脚本未加载，本页图表全部不可用；表格与数字不受影响。
           </div>`);
      }
    }
    return;
  }
  Plotly.react(divId, data, { ...LAYOUT, ...extraLayout }, {
    responsive: true,
    displayModeBar: false,
    ...config,
  });
}

/** 数据缺失时给出明确空状态, 避免页面显示一片 '--' 像是崩了 */
function renderEmpty(divId, title, hint) {
  const el = document.getElementById(divId);
  if (!el) return;
  el.innerHTML = `<div class="empty-state">
    <div class="empty-title">${title}</div>
    ${hint ? `<div class="empty-hint">${hint}</div>` : ''}
  </div>`;
}

/* ============================================
   3. 布局渲染
   ============================================ */
function renderLayout(activeKey) {
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
    </header>`;

  let sidebar = '<nav id="sidebar">';
  NAV_CONFIG.forEach(sec => {
    sidebar += '<div class="nav-section">';
    sidebar += `<div class="nav-section-title">${sec.section}</div>`;
    sec.items.forEach(item => {
      const cls = item.key === activeKey ? 'nav-link active' : 'nav-link';
      const [href, hash] = item.href.split('#');
      sidebar += `<a class="${cls}" href="${href}"${hash ? ` data-tab-target="${hash}"` : ''}>` +
        `<span class="nav-icon">${item.icon}</span>` +
        `<span class="nav-link-label">${item.label}</span></a>`;
    });
    sidebar += '</div>';
  });
  sidebar += '</nav>';

  const footer = `
    <footer id="footer">
      <span>龙头量化 · 行业龙头策略系统<span id="data-range"></span></span>
      <span id="last-update">--</span>
    </footer>`;

  document.body.insertAdjacentHTML('afterbegin', topbar + sidebar);
  document.body.insertAdjacentHTML('beforeend', footer);

  /* --- 时钟 --- */
  const updateClock = () => {
    const now = new Date();
    document.getElementById('clock').textContent =
      `${String(now.getHours()).padStart(2, '0')}:` +
      `${String(now.getMinutes()).padStart(2, '0')}:` +
      `${String(now.getSeconds()).padStart(2, '0')}`;
  };
  updateClock();
  setInterval(updateClock, 1000);

  /* --- 市场状态 --- */
  const updateMarketStatus = () => {
    const now = new Date();
    const hm = now.getHours() * 60 + now.getMinutes();
    const isOpen = now.getDay() >= 1 && now.getDay() <= 5 &&
      ((hm >= 570 && hm <= 690) || (hm >= 780 && hm <= 900));
    document.getElementById('market-status').className =
      `market-status ${isOpen ? 'open' : 'closed'}`;
    document.getElementById('market-label').textContent = isOpen ? 'OPEN' : 'CLOSED';
  };
  updateMarketStatus();
  setInterval(updateMarketStatus, 60000);

  document.getElementById('last-update').textContent =
    `Updated: ${new Date().toLocaleString('zh-CN')}`;

  /* --- 带 hash 的导航项: 交给目标页面的 hash 路由处理 --- */
  document.querySelectorAll('[data-tab-target]').forEach(a => {
    a.addEventListener('click', () => {
      // 让浏览器正常改 hash, 由目标页 hashchange 监听响应
    });
  });
}

/**
 * 页签路由: 支持 location.hash 直达 + hashchange,
 * 使 index.html#tab-backtest 这类跨页跳转可靠生效。
 * @param {string} prefix hash 前缀, 如 'tab-'
 * @param {(name:string)=>void} onSwitch 切换回调
 */
function bindTabRoute(prefix, onSwitch) {
  const apply = () => {
    const h = location.hash.replace('#', '');
    if (h.startsWith(prefix)) onSwitch(h.slice(prefix.length));
  };
  window.addEventListener('hashchange', apply);
  apply();
}

/* ============================================
   4. 数据加载
   ============================================ */
const DataLoader = {
  cache: {},

  async load(name) {
    if (this.cache[name]) return this.cache[name];
    try {
      const res = await fetch(`data/${name}.json`);
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      this.cache[name] = data;
      return data;
    } catch (e) {
      console.warn(`[DataLoader] ${name}.json:`, e.message);
      return null;
    }
  },

  /** 同 load, 但返回 HTTP 状态, 便于区分"文件未生成(404)"和"解析失败" */
  async loadStatus(name) {
    if (this.cache[name]) return { status: 200, data: this.cache[name] };
    try {
      const res = await fetch(`data/${name}.json`);
      if (!res.ok) return { status: res.status, data: null };
      const data = await res.json();
      this.cache[name] = data;
      return { status: 200, data };
    } catch (e) {
      return { status: 0, data: null };
    }
  },

  async loadMulti(names) {
    const results = await Promise.all(names.map(n => this.load(n)));
    return Object.fromEntries(names.map((n, i) => [n, results[i]]));
  },

  /** 情绪终端需要的一揽子数据包 */
  async loadAll() {
    const names = ['sentiment', 'monthly', 'markers', 'backtest', 'trades', 'walkforward', 'yearly'];
    return this.loadMulti(names);
  },
};

/* ============================================
   5. 工具函数
   ============================================ */
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

/** 涨跌染色: 正红负绿(A股), 零或无值不着色 */
function chgHtml(v, decimals = 2) {
  if (v === null || v === undefined || isNaN(v)) return '--';
  const cls = v > 0 ? 'q-up' : v < 0 ? 'q-down' : '';
  return `<span class="${cls}">${v > 0 ? '+' : ''}${Number(v).toFixed(decimals)}%</span>`;
}

function regimeBadge(regime) {
  const cls = regime === 'BULL' ? 'bull' : regime === 'BEAR' ? 'bear' : 'shock';
  return `<span class="badge ${cls}">${regime}</span>`;
}

function showError(msg) {
  const main = document.getElementById('main');
  if (!main) return;
  main.innerHTML = `<div class="empty-state error-state">
    <div class="empty-title">⚠ 数据加载失败</div>
    <div class="empty-hint">${msg}</div>
  </div>`;
}