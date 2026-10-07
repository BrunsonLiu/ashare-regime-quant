# -*- coding: utf-8 -*-
"""每日决策助手测试: 环境→操作映射、主线行业、持仓检查逻辑"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: F401

from src.utils.market_env import ENV_DESC, ENV_EXPOSURE


class TestDailyAssistantLogic(unittest.TestCase):

    def test_environment_action_mapping(self):
        """每个环境都有描述和仓位映射(工具输出依赖)"""
        for env in ('A', 'B', 'C', 'D'):
            self.assertIn(env, ENV_DESC)
            self.assertIn(env, ENV_EXPOSURE)
        # 关键: A可持仓, D空仓
        self.assertGreater(ENV_EXPOSURE['A'], 0)
        self.assertEqual(ENV_EXPOSURE['D'], 0.0)

    def test_industry_heat_computation(self):
        """行业热度 = 涨停家数 + 连板高度*3"""
        from src.backtest.sentiment_sector import build_industry_heat
        heat = build_industry_heat()
        self.assertGreater(len(heat), 0)
        for col in ('date', 'industry', 'zt_cnt', 'max_lb'):
            self.assertIn(col, heat.columns)
        # 家数/连板为正
        self.assertTrue((heat['zt_cnt'] >= 1).all())
        self.assertTrue((heat['max_lb'] >= 1).all())

    def test_leaders_filter_by_industry(self):
        """建议龙头必须来自指定行业"""
        from src.daily_assistant import _leaders_in_industries
        leaders = _leaders_in_industries(['C39计算机、通信和其他电子设备制造业'], k=3)
        self.assertGreater(len(leaders), 0)
        self.assertTrue((leaders['industry'] == 'C39计算机、通信和其他电子设备制造业').all())

    def test_daily_report_runs(self):
        """端到端: 报告能在真实数据上生成(不抛异常)"""
        from src.daily_assistant import daily_report
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        # 需要指数缓存; CI无则跳过
        from config import DATA_DIR
        if not os.path.exists(os.path.join(DATA_DIR, 'index_000001.csv')):
            self.skipTest('无指数缓存')
        with redirect_stdout(buf):
            res = daily_report(['600519'])
        self.assertIn('env', res)
        self.assertIn(res['env'], ('A', 'B', 'C', 'D', 'WARMUP'))


if __name__ == '__main__':
    unittest.main()
