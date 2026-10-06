"""
直接HTTP数据获取器
绕过AKShare的网络限制，直接请求东方财富API

网络策略：
- 使用 requests.Session 保持连接
- 自动重试3次
- 备用接口降级
"""
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.eastmoney.com/',
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


class DirectDataFetcher:
    """直接HTTP获取东方财富数据，带重试"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        # 连接池
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5, pool_maxsize=10, max_retries=3
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def _fetch(self, url, timeout=10, retries=3):
        """带重试的请求"""
        last_err = None
        for i in range(retries):
            try:
                r = self.session.get(url, timeout=timeout)
                return r.json()
            except Exception as e:
                last_err = e
                if i < retries - 1:
                    time.sleep(0.5 * (i + 1))
        print(f"请求失败({retries}次): {url[:60]} - {last_err}")
        return None

    # ── K线数据（最稳定）──────────────────────────────

    def get_kline(self, code, period='daily', start_date='20200101', end_date='20500101', adjust='qfq'):
        """
        获取K线数据（东方财富K线API，最稳定的接口）
        code: 股票代码，如 '000001'
        period: daily/weekly/monthly/min60/min30/min15
        start_date/end_date: YYYYMMDD
        adjust: qfq/hfq/''
        """
        code = str(code).zfill(6)
        market = '1' if code.startswith('6') else '0'

        period_map = {
            'daily': '101', 'weekly': '102', 'monthly': '103',
            'min60': '60', 'min30': '30', 'min15': '15',
        }
        klt = period_map.get(period, '101')
        fqt = {'qfq': '1', 'hfq': '2'}.get(adjust, '0')

        url = (
            'https://push2his.eastmoney.com/api/qt/stock/kline/get'
            f'?secid={market}.{code}'
            '&fields1=f1,f2,f3,f4,f5,f6'
            '&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'
            f'&klt={klt}&fqt={fqt}&beg={start_date}&end={end_date}&lmt=1000000'
        )

        data = self._fetch(url)
        if data is None or data.get('data') is None:
            return pd.DataFrame()

        klines = data['data'].get('klines', [])
        if not klines:
            return pd.DataFrame()

        rows = []
        for k in klines:
            p = k.split(',')
            rows.append({
                'date': p[0], 'open': float(p[1]), 'close': float(p[2]),
                'high': float(p[3]), 'low': float(p[4]),
                'volume': int(p[5]), 'amount': float(p[6]),
                'amplitude': float(p[7]) if len(p) > 7 else 0.0,
                'chg_pct': float(p[8]) if len(p) > 8 else 0.0,
                'chg': float(p[9]) if len(p) > 9 else 0.0,
                'turnover': float(p[10]) if len(p) > 10 else 0.0,
            })

        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        return df

    def get_index_kline(self, code, period='daily', start_date='20200101', end_date='20500101'):
        """获取指数K线"""
        return self.get_kline(code, period, start_date, end_date, adjust='')

    # ── 涨停股（东财涨停池，真实涨停口径）───────────────

    def get_limit_up(self, limit=200, date=None):
        """
        获取涨停股列表（push2ex 涨停池，按涨停定义过滤而非涨幅排行）
        返回列: code/name/close/chg_pct/amount/turnover/first_seal_time/lianban
        """
        date = date or datetime.now().strftime('%Y%m%d')
        url = (
            'https://push2ex.eastmoney.com/getTopicZTPool'
            '?ut=7eea1ed2ed6e33cc8fbb3aa52507d0b4&dpt=wz.ztzt'
            f'&Pageindex=0&pagesize={max(int(limit), 1)}&sort=fbt%3Aasc&date={date}'
        )
        data = self._fetch(url)
        if data is None or data.get('data') is None:
            return pd.DataFrame()

        pool = data['data'].get('pool') or []
        rows = []
        for item in pool:
            p = item.get('p')
            rows.append({
                'code': str(item.get('c', '')).zfill(6),
                'name': item.get('n', ''),
                'close': round(p / 1000, 2) if p else None,
                'chg_pct': item.get('zdp'),
                'amount': item.get('amount'),
                'turnover': item.get('hs'),
                'first_seal_time': item.get('fbt'),
                'lianban': item.get('lbc', 1),
            })
        return pd.DataFrame(rows)

    def get_limit_down(self, limit=200, date=None):
        """获取跌停股列表（push2ex 跌停池，真实跌停口径）"""
        date = date or datetime.now().strftime('%Y%m%d')
        url = (
            'https://push2ex.eastmoney.com/getTopicDTPool'
            '?ut=7eea1ed2ed6e33cc8fbb3aa52507d0b4&dpt=wz.ztzt'
            f'&Pageindex=0&pagesize={max(int(limit), 1)}&sort=fund%3Aasc&date={date}'
        )
        data = self._fetch(url)
        if data is None or data.get('data') is None:
            return pd.DataFrame()

        pool = data['data'].get('pool') or []
        rows = []
        for item in pool:
            p = item.get('p')
            rows.append({
                'code': str(item.get('c', '')).zfill(6),
                'name': item.get('n', ''),
                'close': round(p / 1000, 2) if p else None,
                'chg_pct': item.get('zdp'),
                'amount': item.get('amount'),
                'turnover': item.get('hs'),
                'lianban': item.get('lbc', 1),
            })
        return pd.DataFrame(rows)

    # ── 指数实时行情（东方财富stock/get）─────────────

    def get_index_realtime(self, codes=None):
        """
        获取指数实时行情
        codes: list，如 ['000001', '399001', '399006']
        """
        if codes is None:
            codes = ['000001', '399001', '399006']

        rows = []
        for code in codes:
            # 指数 secid: 399xxx(深成指/创业板指等)为深市 0, 000xxx(上证/沪深300等)为沪市 1
            market = '0' if code.startswith('399') else '1'
            url = (
                'https://push2.eastmoney.com/api/qt/stock/get'
                f'?secid={market}.{code}'
                '&fields=f2,f3,f4,f5,f6,f7,f8,f43,f44,f45,f46,f47,f57,f58'
            )
            data = self._fetch(url)
            if data and data.get('data'):
                d = data['data']
                rows.append({
                    'code': code,
                    'name': d.get('f58', ''),
                    'close': d.get('f2'),
                    'chg_pct': d.get('f3'),
                    'chg': d.get('f4'),
                    'volume': d.get('f6'),
                    'amount': d.get('f7'),
                    'pre_close': d.get('f18'),
                    'open': d.get('f43'),
                    'high': d.get('f44'),
                    'low': d.get('f45'),
                    'high52w': d.get('f46'),
                    'low52w': d.get('f47'),
                })
            time.sleep(0.2)

        return pd.DataFrame(rows)

    # ── 个股实时行情（东方财富stock/get，逐个查）───

    def get_stock_realtime(self, code):
        """获取单只个股实时行情"""
        code = str(code).zfill(6)
        market = '1' if code.startswith('6') else '0'
        url = (
            'https://push2.eastmoney.com/api/qt/stock/get'
            f'?secid={market}.{code}'
            '&fields=f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f62,f128,f136'
        )
        data = self._fetch(url)
        if data is None or data.get('data') is None:
            return {}
        d = data['data']
        return {
            'code': code,
            'name': d.get('f14', ''),
            'close': d.get('f2'),
            'chg_pct': d.get('f3'),
            'chg': d.get('f4'),
            'open': d.get('f15'),
            'high': d.get('f17'),
            'low': d.get('f16'),
            'volume': d.get('f6'),
            'amount': d.get('f7'),
            'turnover': d.get('f10'),
            'pe': d.get('f9'),
            'pb': d.get('f23'),
            'mkt_cap': d.get('f20'),
            'north_net': d.get('f62'),
        }

    # ── 板块/行业涨跌排行 ─────────────────────────

    def get_sector_ranking(self, top_n=20):
        """获取涨幅前N的板块"""
        url = (
            'https://push2.eastmoney.com/api/qt/clist/get'
            '?pn=1'
            f'&pz={top_n}'
            '&po=1&np=1&fltt=2&invt=2&fid=f3'
            '&fs=m:90+t:2+f:!50,m:90+t:3+f:!50'
            '&fields=f2,f3,f4,f5,f6,f12,f14,f20,f21'
        )
        data = self._fetch(url)
        if data is None or data.get('data') is None:
            return pd.DataFrame()
        items = data['data'].get('diff', [])
        rows = []
        for item in items:
            rows.append({
                '板块代码': item.get('f12', ''),
                '板块名称': item.get('f14', ''),
                '涨跌幅': item.get('f3'),
                '涨跌额': item.get('f4'),
                '成交额': item.get('f6'),
                '上涨家数': item.get('f20'),
                '下跌家数': item.get('f21'),
            })
        return pd.DataFrame(rows)

    # ── 主力资金流向 ──────────────────────────────

    def get_money_flow(self):
        """获取今日主力资金流向"""
        url = (
            'https://push2.eastmoney.com/api/qt/clist/get'
            '?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f62'
            '&fs=m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23'
            '&fields=f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87'
        )
        data = self._fetch(url)
        if data is None or data.get('data') is None:
            return pd.DataFrame()
        items = data['data'].get('diff', [])
        rows = []
        for item in items:
            rows.append({
                'code': str(item.get('f12', '')).zfill(6),
                'name': item.get('f14', ''),
                'close': item.get('f2'),
                'chg_pct': item.get('f3'),
                'main_net': item.get('f62'),
                'super_net': item.get('f66'),
                'retail_net': item.get('f69'),
            })
        return pd.DataFrame(rows)

    # ── 综合市场概览 ──────────────────────────────

    def get_market_overview(self):
        """
        获取市场综合概览
        返回：主要指数 + 涨跌停统计 + 主线板块
        """
        # 指数
        indices = self.get_index_realtime(['000001', '399001', '399006', '000300', '000016'])
        # 涨停/跌停
        lu = self.get_limit_up(limit=500)
        ld = self.get_limit_down(limit=500)
        # 板块
        sectors = self.get_sector_ranking(top_n=15)

        return {
            'indices': indices,
            'limit_up_count': len(lu),
            'limit_down_count': len(ld),
            'sectors': sectors,
        }


# ── 全局实例 ───────────────────────────────────

_fetcher = None


def get_fetcher():
    global _fetcher
    if _fetcher is None:
        _fetcher = DirectDataFetcher()
    return _fetcher
