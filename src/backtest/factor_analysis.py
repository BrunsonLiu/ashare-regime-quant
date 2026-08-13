"""
因子分析模块 - 实践论的核心
检验因子是否有效，失效的及时淘汰

指标：
- IC (Information Coefficient): 因子值与未来收益的相关性
- IR (Information Ratio): IC的均值/标准差，衡量稳定性
- IC胜率: IC>0的比例
- 分组收益: 按因子值分5组，看多空收益差
"""
import pandas as pd
import numpy as np


class FactorAnalysis:
    """因子有效性分析"""

    @staticmethod
    def calc_ic(factor_values, forward_returns, method='spearman'):
        """
        计算IC（信息系数）
        参数:
            factor_values: Series, 因子值
            forward_returns: Series, 未来N日收益率
            method: 'spearman' 或 'pearson'
        返回: float, IC值
        """
        mask = factor_values.notna() & forward_returns.notna()
        if mask.sum() < 10:
            return np.nan

        f = factor_values[mask]
        r = forward_returns[mask]

        if method == 'spearman':
            from scipy.stats import spearmanr
            ic, _ = spearmanr(f, r)
        else:
            ic = f.corr(r)

        return ic

    @staticmethod
    def calc_ic_series(factor_df, return_df, periods=[1, 5, 10, 20]):
        """
        计算多周期IC序列
        参数:
            factor_df: DataFrame[date, code, factor_value]
            return_df: DataFrame[date, code, close]
            periods: 预测周期列表
        返回: DataFrame[date, period, ic]
        """
        results = []

        # 合并因子和价格
        merged = factor_df.merge(return_df, on=['date', 'code'], how='inner')
        merged = merged.sort_values(['code', 'date'])

        for period in periods:
            # 计算未来N日收益
            merged[f'fwd_ret_{period}'] = merged.groupby('code')['close'].pct_change(period).shift(-period)

        for date in merged['date'].unique():
            day_data = merged[merged['date'] == date]
            for period in periods:
                ret_col = f'fwd_ret_{period}'
                ic = FactorAnalysis.calc_ic(
                    day_data['factor_value'],
                    day_data[ret_col]
                )
                results.append({
                    'date': date,
                    'period': period,
                    'ic': ic
                })

        return pd.DataFrame(results)

    @staticmethod
    def calc_ir(ic_series):
        """
        计算IR（信息比率）
        IR = IC均值 / IC标准差
        """
        ic = ic_series.dropna()
        if len(ic) < 5:
            return np.nan

        mean_ic = ic.mean()
        std_ic = ic.std()

        if std_ic == 0:
            return 0

        return mean_ic / std_ic

    @staticmethod
    def ic_summary(ic_df):
        """
        IC/IR汇总统计
        输入: calc_ic_series的结果
        """
        summary = []
        for period in ic_df['period'].unique():
            sub = ic_df[ic_df['period'] == period]['ic']

            mean_ic = sub.mean()
            std_ic = sub.std()
            ir = mean_ic / std_ic if std_ic > 0 else 0
            win_rate = (sub > 0).mean() if len(sub) > 0 else 0

            # 有效性判断
            if abs(ir) > 0.5 and win_rate > 0.55:
                verdict = "[OK] 有效"
            elif abs(ir) > 0.3:
                verdict = "[!!] 一般"
            else:
                verdict = "[X] 无效"

            summary.append({
                'period': f"{period}日",
                'IC均值': round(mean_ic, 4),
                'IC标准差': round(std_ic, 4),
                'IR': round(ir, 4),
                'IC胜率': f"{win_rate*100:.1f}%",
                '评估': verdict
            })

        return pd.DataFrame(summary)

    @staticmethod
    def quantile_analysis(factor_df, return_df, n_groups=5, period=5):
        """
        分组收益分析
        按因子值分N组，看各组收益，检验单调性
        """
        merged = factor_df.merge(return_df[['date', 'code', 'close']], on=['date', 'code'])
        merged = merged.sort_values(['code', 'date'])
        merged['fwd_ret'] = merged.groupby('code')['close'].pct_change(period).shift(-period)

        results = []
        for date in merged['date'].unique():
            day_data = merged[merged['date'] == date].dropna(subset=['factor_value', 'fwd_ret'])
            if len(day_data) < n_groups * 5:
                continue

            day_data['group'] = pd.qcut(day_data['factor_value'], n_groups, labels=False)
            group_ret = day_data.groupby('group')['fwd_ret'].mean()

            results.append({
                'date': date,
                'long_ret': group_ret.get(n_groups - 1, np.nan),   # 最高组
                'short_ret': group_ret.get(0, np.nan),              # 最低组
                'long_short': group_ret.get(n_groups - 1, 0) - group_ret.get(0, 0),
            })

        result_df = pd.DataFrame(results)

        if len(result_df) == 0:
            return None

        summary = {
            '多组平均收益': f"{result_df['long_ret'].mean()*100:.2f}%",
            '空组平均收益': f"{result_df['short_ret'].mean()*100:.2f}%",
            '多空收益差': f"{result_df['long_short'].mean()*100:.2f}%",
            '多空胜率': f"{(result_df['long_short']>0).mean()*100:.1f}%",
            '评估': "[OK] 单调有效" if result_df['long_short'].mean() > 0.01 else "[X] 无明显区分度"
        }

        return summary
