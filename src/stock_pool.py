"""
股票池过滤模块
按Brunson的规则构建可用股票池
"""
import pandas as pd
from config import POOL_CONFIG
from src.data_loader import DataLoader


class StockPool:
    """股票池构建与过滤"""

    def __init__(self):
        self.loader = DataLoader()
        self.config = POOL_CONFIG

    def build(self):
        """
        构建股票池：
        1. 全市场股票列表
        2. 排除ST/退市/北交所
        3. 流动性过滤（成交额门槛）
        4. 保存结果
        """
        print("=== 构建股票池 ===")

        # 1. 获取全部股票
        all_stocks = self.loader.get_stock_list()
        print(f"全市场股票: {len(all_stocks)}")
        if len(all_stocks) == 0:
            print("错误：股票列表为空")
            return None

        # 2. 基础过滤
        pool = self._basic_filter(all_stocks)
        print(f"基础过滤后: {len(pool)}")

        # 3. 流动性过滤
        pool = self._liquidity_filter(pool)
        if pool is None:
            pool = self._basic_filter(all_stocks)
        print(f"流动性过滤后: {len(pool)}")

        return pool

    def _basic_filter(self, df):
        """基础过滤：ST、退市、板块"""
        cfg = self.config

        # 排除ST
        if cfg['exclude_st']:
            df = df[~df['name'].str.contains(r'ST|^\*ST', case=False, na=False)]

        # 排除退市
        if cfg['exclude_delisting']:
            df = df[~df['name'].str.contains(r'退', na=False)]

        # 只保留指定板块
        if cfg['board_filter']:
            mask = df['code'].apply(
                lambda c: any(c.startswith(p) for p in cfg['board_filter'])
            )
            df = df[mask]

        return df.reset_index(drop=True)

    def _liquidity_filter(self, df):
        """流动性过滤：成交额门槛；网络失败时跳过过滤"""
        try:
            realtime = self.loader.get_realtime_quote()

            # 网络失败或空数据则跳过流动性过滤
            if realtime is None or len(realtime) == 0:
                print("  流动性过滤：实时行情获取失败，跳过（保留现有候选）")
                return df

            # 只保留股票池内的
            realtime = realtime[realtime['code'].isin(df['code'])]

            # 成交额门槛
            min_amt = self.config['min_amount']
            if 'amount' in realtime.columns:
                realtime = realtime[realtime['amount'] >= min_amt]

            # 合并回股票池
            cols = ['code', 'amount', 'turnover', 'pe', 'pb', 'total_mv', 'circ_mv']
            cols = [c for c in cols if c in realtime.columns]
            if not cols:
                print("  流动性过滤：字段不完整，跳过")
                return df

            df = df.merge(realtime[cols], on='code', how='inner')
            print(f"  流动性过滤后剩余: {len(df)}只")

        except Exception as e:
            print(f"  流动性过滤异常: {e}")

        return df.reset_index(drop=True)

    def save(self, pool):
        """保存股票池"""
        if pool is None or len(pool) == 0:
            print("股票池为空，跳过保存")
            return
        path = f"{self.loader.data_dir}/stock_pool.csv"
        pool.to_csv(path, index=False, encoding='utf-8-sig')
        print(f"股票池已保存: {path}")

    def load(self):
        """加载已保存的股票池（code自动补零为6位）"""
        path = f"{self.loader.data_dir}/stock_pool.csv"
        try:
            df = pd.read_csv(path, dtype={'code': str})
            # code 可能是整数，补零为6位字符串
            df['code'] = df['code'].astype(str).str.zfill(6)
            return df
        except FileNotFoundError:
            print("股票池未构建，请先运行 build()")
            return None


if __name__ == "__main__":
    pool_builder = StockPool()
    pool = pool_builder.build()
    pool_builder.save(pool)

    # 打印成交额前20
    if pool is not None and 'amount' in pool.columns:
        top20 = pool.nlargest(20, 'amount')
        print("\n成交额前20：")
        print(top20[['code', 'name', 'amount', 'turnover']].to_string(index=False))
