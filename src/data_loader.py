"""
数据加载器
双数据源策略：
  - Baostock：主力数据源（K线、股票列表、行业分类，稳定免费）
  - AKShare：补充数据源（实时行情、涨跌停、情绪数据）
"""
import akshare as ak
import baostock as bs
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from config import DATA_DIR, DAILY_DIR, DATA_CONFIG


class DataLoader:
    """A股数据加载与缓存管理"""

    def __init__(self):
        self.data_dir = DATA_DIR
        self.daily_dir = DAILY_DIR
        self._bs_logged_in = False
        self._industry_cache = None

    # ── Baostock 登录 ─────────────────────────────

    def _bs_login(self):
        """登录 Baostock（重复调用安全；失败不置位，允许下次重试）"""
        if self._bs_logged_in:
            return
        try:
            lg = bs.login()
            if lg.error_code == '0':
                self._bs_logged_in = True
            else:
                print(f"[!!] baostock 登录失败: {lg.error_msg}（后续调用将重试）")
        except Exception as e:
            print(f"[!!] baostock 登录异常: {e}")

    # ── 股票列表 ─────────────────────────────────

    def get_stock_list(self):
        """
        获取A股股票列表。
        优先从 stock_pool.csv 读取（已过滤 ST/退市/北交所），
        code 列自动补零为6位字符串。
        """
        pool_path = os.path.join(self.data_dir, 'stock_pool.csv')
        if os.path.exists(pool_path):
            try:
                df = pd.read_csv(pool_path, encoding='utf-8-sig')
                if 'code' in df.columns:
                    # code 列可能是整数，补零成6位
                    df['code'] = df['code'].astype(str).str.zfill(6)
                    return df[['code', 'name']].reset_index(drop=True)
            except Exception:
                pass
        # 回退：从 Baostock 查询（非交易日 query_all_stock 返回空，向前回溯最近交易日）
        self._bs_login()
        df = pd.DataFrame()
        for back in range(7):
            day = (datetime.now() - timedelta(days=back)).strftime('%Y-%m-%d')
            rs = bs.query_all_stock(day=day)
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if rows:
                df = pd.DataFrame(rows, columns=rs.fields)
                break
        if len(df) == 0:
            print("[!!] baostock 股票列表为空（非交易日或未登录）")
            return df
        df = df[df['code'].str.contains(r'sh\.') | df['code'].str.contains(r'sz\.')].copy()
        if 'tradeStatus' in df.columns:
            df = df[df['tradeStatus'].astype(str) == '1']
        df['code'] = df['code'].str.replace(r'sh.', '', regex=False).str.replace(r'sz.', '', regex=False)
        df = df.rename(columns={'code_name': 'name'})
        return df[['code', 'name']].reset_index(drop=True)

    # ── 行业分类 ─────────────────────────────────

    def get_industry(self):
        """获取申万行业分类（Baostock，5536条）"""
        if self._industry_cache is not None:
            return self._industry_cache
        self._bs_login()
        rs = bs.query_stock_industry()
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        df = pd.DataFrame(rows, columns=rs.fields)
        # 标准化code（去掉sh./sz.前缀）
        df['code_std'] = df['code'].str.replace('sh.', '').str.replace('sz.', '')
        self._industry_cache = df
        return df

    # ── 日线K线（核心方法）────────────────────────

    def get_daily_data(self, code, days=None):
        """
        获取单只股票日线数据（Baostock为主，AKShare备用）
        返回: DataFrame[date, open, high, low, close, volume, amount]
        """
        if days is None:
            days = DATA_CONFIG['history_days']

        # 1. 优先从缓存读
        cache = self.load_cache(code)
        if cache is not None and len(cache) >= days * 0.8:
            # 缓存够新就不重下
            if len(cache) > 0:
                last_date = pd.to_datetime(cache['date']).max()
                if (datetime.now().date() - last_date.date()).days < 3:
                    return cache

        # 2. Baostock 获取
        df = self._get_daily_baostock(code, days)
        if df is not None and len(df) > 10:
            self._save_cache(code, df)
            return df

        # 3. AKShare 备用
        df = self._get_daily_akshare(code, days)
        if df is not None and len(df) > 10:
            self._save_cache(code, df)
            return df

        return None

    def _get_daily_baostock(self, code, days=None):
        """Baostock 获取日线"""
        try:
            self._bs_login()
            bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days or DATA_CONFIG['history_days'])).strftime('%Y-%m-%d')

            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount,turnover,pctChg",
                start_date=start_date, end_date=end_date,
                frequency="d"
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                return None

            df = pd.DataFrame(rows, columns=rs.fields)
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover', 'pctChg']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['date'] = pd.to_datetime(df['date'])
            df['code'] = code
            df = df.dropna(subset=['close'])
            return df
        except Exception:
            return None

    def _get_daily_akshare(self, code, days=None):
        """AKShare 获取日线（备用）"""
        try:
            if days is None:
                days = DATA_CONFIG['history_days']
            symbol = f"sh{code}" if code.startswith('6') else f"sz{code}"
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=DATA_CONFIG['adjust']
            )
            if df is None or len(df) == 0:
                return None
            df['code'] = code
            df['date'] = pd.to_datetime(df['date'])
            # 统一为 baostock 缓存 schema: 补 pctChg, turnover 由小数转百分数
            if 'pctChg' not in df.columns:
                df['pctChg'] = df['close'].pct_change() * 100
            if 'turnover' in df.columns and df['turnover'].max() is not None and df['turnover'].max() <= 1.5:
                df['turnover'] = df['turnover'] * 100
            return df
        except Exception as e:
            print(f"[!!] akshare 日线获取失败 {code}: {e}")
            return None

    def _save_cache(self, code, df):
        """保存到本地缓存"""
        try:
            os.makedirs(self.daily_dir, exist_ok=True)
            cache_path = os.path.join(self.daily_dir, f"{code}.csv")
            df.to_csv(cache_path, index=False, encoding='utf-8-sig')
        except Exception as e:
            print(f"[!!] 缓存写入失败 {code}: {e}")

    def load_cache(self, code):
        """从本地缓存加载"""
        cache_path = os.path.join(self.daily_dir, f"{code}.csv")
        if os.path.exists(cache_path):
            try:
                df = pd.read_csv(cache_path, parse_dates=['date'])
                return df
            except Exception:
                pass
        return None

    def get_daily_batch(self, codes, days=None):
        """批量下载日线数据"""
        results = {}
        failed = []
        total = len(codes)
        for i, code in enumerate(codes):
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{total}")
            try:
                df = self.get_daily_data(code, days)
                if df is not None:
                    results[code] = df
                else:
                    failed.append(code)
            except Exception as e:
                failed.append(code)
                print(f"[!!] 下载失败 {code}: {e}")
        if failed:
            print(f"失败 {len(failed)} 只(前10): {failed[:10]}")
        print(f"完成: {len(results)}/{total}")
        return results

    # ── 指数数据 ─────────────────────────────────

    def get_index_data(self, index_code="000001", days=None):
        """
        获取指数数据（默认上证指数）
        000001=上证 399001=深成指 399006=创业板指
        """
        # Baostock 上证指数代码 sh.000001
        if index_code == "000001":
            bs_code = "sh.000001"
        elif index_code == "399001":
            bs_code = "sz.399001"
        elif index_code == "399006":
            bs_code = "sz.399006"
        elif index_code == "000300":
            bs_code = "sh.000300"
        elif index_code == "000016":
            bs_code = "sh.000016"
        else:
            bs_code = f"sh.{index_code}"

        try:
            self._bs_login()
            if days is None:
                days = DATA_CONFIG['history_days']
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume,amount,pctChg",
                start_date=start_date, end_date=end_date,
                frequency="d"
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                return None

            df = pd.DataFrame(rows, columns=rs.fields)
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'pctChg']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['date'] = pd.to_datetime(df['date'])
            df = df.dropna(subset=['close'])
            return df
        except Exception as e:
            # 备用 AKShare
            try:
                if days is None:
                    days = DATA_CONFIG['history_days']
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
                prefix = 'sz' if index_code.startswith('399') else 'sh'
                df = ak.stock_zh_index_daily(symbol=f"{prefix}{index_code}")
                if df is None or len(df) == 0:
                    return None
                df['date'] = pd.to_datetime(df['date'])
                return df
            except Exception as e2:
                print(f"[!!] 指数数据获取失败 {index_code}: {e} / {e2}")
                return None

    # ── 实时行情（AKShare，东方财富）──────────────

    def get_realtime_quote(self):
        """获取全市场实时行情（AKShare）"""
        try:
            df = ak.stock_zh_a_spot_em()
            df = df.rename(columns={
                '代码': 'code', '名称': 'name', '最新价': 'close',
                '涨跌幅': 'pct_chg', '涨跌额': 'chg',
                '成交量': 'volume', '成交额': 'amount',
                '振幅': 'amplitude', '最高': 'high', '最低': 'low',
                '今开': 'open', '昨收': 'pre_close',
                '量比': 'volume_ratio', '换手率': 'turnover',
                '市盈率-动态': 'pe', '市净率': 'pb',
                '总市值': 'total_mv', '流通市值': 'circ_mv'
            })
            df['code'] = df['code'].astype(str).str.zfill(6)
            return df
        except Exception as e:
            print(f"实时行情获取失败: {e}")
            return pd.DataFrame()

    # ── 北向资金 ─────────────────────────────────

    def get_north_flow(self, days=30):
        """获取北向资金历史数据（AKShare）"""
        try:
            df = ak.stock_hsgt_hist_em(symbol="北向资金")
            if df is not None and len(df) > 0:
                if '日期' in df.columns:
                    df = df.sort_values('日期')
                return df.tail(days)
        except Exception as e:
            print(f"北向资金数据获取失败: {e}")
        return None

    # ── 龙虎榜 ─────────────────────────────────

    def get_dragon_tiger(self, date_str=None):
        """获取龙虎榜数据"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')
        try:
            df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
            return df
        except Exception:
            return None

    # ── 外围市场 ─────────────────────────────────

    def get_us_index(self, symbol="美元指数"):
        """获取外围指数数据（AKShare index_global_hist_em）"""
        try:
            df = ak.index_global_hist_em(symbol=symbol)
            if df is not None and len(df) > 0:
                df['date'] = pd.to_datetime(df['日期'])
                rename_map = {'收盘': 'close', '开盘': 'open', '最高': 'high', '最低': 'low', '涨跌幅': 'pct_chg'}
                cols = [c for c in rename_map.keys() if c in df.columns]
                result = df[['date'] + cols].rename(columns=rename_map)
                return result
        except Exception:
            pass
        return None

    def get_global_overview(self):
        """
        获取外围市场全景（双数据源兜底）。
        标普500/恒生指数走AKShare index_global_hist_em，
        美元指数走新浪裸requests（AKShare走代理被封），
        北向资金走AKShare。
        """
        result = {}
        # 1. 标普500 / 恒生指数（AKShare，带涨跌幅——外围综合判断依赖这两个键）
        for name in ('标普500', '恒生指数'):
            try:
                df = self.get_us_index(symbol=name)
                if df is not None and len(df) > 1:
                    row = df.iloc[-1]
                    chg = row.get('pct_chg')
                    result[name] = {
                        'close': float(row['close']),
                        'chg_pct': round(float(chg), 2) if pd.notna(chg) else None,
                        'date': str(row['date'])[:10],
                    }
            except Exception as e:
                print(f"[!!] {name} 数据获取失败: {e}")
        # 2. 美元指数（新浪裸requests；hq.sinajs.cn 要求新浪域 Referer）
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/',
            }
            import requests
            r = requests.get('https://hq.sinajs.cn/list=s_ud', headers=headers, timeout=5)
            if r.status_code == 200 and 's_ud' in r.text:
                parts = r.text.strip().split('="')[1].split('"')[0].split(',')
                if len(parts) >= 3:
                    result['美元指数'] = {'close': float(parts[0]), 'note': '间接数据'}
        except Exception as e:
            print(f"[!!] 美元指数数据获取失败: {e}")
        # 2. 北向资金（AKShare，主力渠道）
        try:
            df = ak.stock_hsgt_hist_em(symbol='北向资金')
            if df is not None and len(df) >= 2:
                df = df.sort_values('日期')
                row = df.iloc[-1]
                # 找可用列
                for col in ['当日资金流入', '持股市值']:
                    if col in df.columns:
                        val = row.get(col)
                        if pd.notna(val) and val != 0:
                            result['北向资金'] = {
                                'value': round(float(val), 2),
                                'date': str(row.get('日期', ''))[:10],
                            }
                            break
        except Exception:
            pass
        return result
