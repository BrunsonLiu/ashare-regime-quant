"""
因子基类 - 所有因子的抽象接口
"""
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod


class FactorBase(ABC):
    """因子基类"""

    def __init__(self, name):
        self.name = name

    @abstractmethod
    def calculate(self, df):
        """
        计算因子值
        参数: df - 单只股票的日线数据 DataFrame
        返回: pd.Series 或 float
        """
        pass

    def get_latest(self, df):
        """获取最新的因子值"""
        result = self.calculate(df)
        if isinstance(result, pd.Series):
            return result.iloc[-1] if len(result) > 0 else np.nan
        return result


class FactorEngine:
    """因子计算引擎 - 批量计算多只股票的因子"""

    def __init__(self):
        self.factors = {}

    def register(self, factor):
        """注册因子"""
        self.factors[factor.name] = factor

    def calculate_single(self, code, df):
        """计算单只股票的所有因子"""
        result = {'code': code}
        for name, factor in self.factors.items():
            result[name] = factor.get_latest(df)
        return result

    def calculate_batch(self, data_dict):
        """
        批量计算
        参数: data_dict = {code: DataFrame}
        返回: DataFrame, 每行一只股票, 每列一个因子
        """
        results = []
        total = len(data_dict)
        for i, (code, df) in enumerate(data_dict.items()):
            if (i + 1) % 100 == 0:
                print(f"  因子计算进度: {i+1}/{total}")
            if df is None or len(df) == 0:
                continue
            results.append(self.calculate_single(code, df))

        return pd.DataFrame(results)
