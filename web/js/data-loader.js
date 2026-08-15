/* ============================================
   数据加载器 · 异步加载所有 JSON 数据包
   ============================================ */

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
      console.warn(`[DataLoader] ${name}.json load failed:`, e.message);
      return null;
    }
  },
  
  async loadAll() {
    const [sentiment, monthly, markers, backtest, trades, walkforward, yearly] = await Promise.all([
      this.load('sentiment'),
      this.load('monthly'),
      this.load('markers'),
      this.load('backtest'),
      this.load('trades'),
      this.load('walkforward'),
      this.load('yearly'),
    ]);
    return { sentiment, monthly, markers, backtest, trades, walkforward, yearly };
  }
};
