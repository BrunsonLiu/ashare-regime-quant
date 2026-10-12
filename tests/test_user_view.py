# -*- coding: utf-8 -*-
"""
人工观点分类的回归测试 —— 锁定 '不看好' vs '看好' 的子串陷阱
==============================================================
历史 bug: `'看好' in '不看好'` 为 True → 用户填"不看好白酒"时,
bull_industries() 误把白酒当"看好"(同时又是"回避"), 前端显示成红色。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategy.user_view import _classify


def test_bear_variants_are_not_bull():
    for v in ('不看好', '回避', '看空', '谨慎', ''):
        assert _classify(v) != 'bull', f'{v!r} 不应被判为看好'


def test_bull_variants():
    assert _classify('看好') == 'bull'
    assert _classify('看多') == 'bull'


def test_bear_variants():
    assert _classify('不看好') == 'bear'
    assert _classify('回避') == 'bear'
    assert _classify('看空') == 'bear'
    assert _classify('谨慎') == 'bear'


def test_neutral_and_whitespace():
    assert _classify('') == 'neutral'
    assert _classify(None) == 'neutral'
    assert _classify('随便看看') == 'neutral'
    # 前后空白须不影响
    assert _classify('  看好  ') == 'bull'


def test_not_bull_contains_bull_substr():
    """直接锁死那条子串陷阱(即使实现改动也要保证语义)。"""
    assert '看好' in '不看好'          # 前提: 子串关系确实存在
    assert _classify('不看好') == 'bear'  # 但分类必须正确
