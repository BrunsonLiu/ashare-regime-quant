# -*- coding: utf-8 -*-
"""
个人观点输入 —— 把"产业前景判断"交给人, 系统负责纪律与躲坑
================================================================
用户的核心主张(2026-10): 中长线的 edge 来自**产业判断**(力量/趋势/博弈/节奏),
而产业前景是量价数据给不了的 —— 那是人的认知地盘。

分工:
  人   → 出"方向": 看好哪些行业(及其逻辑)
  系统 → 出"纪律+躲坑": 位置是否合适(不接盘)、结构是否健康、怎么分仓

用法:
  python -m src.strategy.user_view            # 查看当前观点 + 系统过滤结果
  (编辑 data/my_view.csv 填入你的观点)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from config import DATA_DIR

VIEW_FILE = os.path.join(DATA_DIR, 'my_view.csv')

TEMPLATE = """industry,view,note
# 在此填入你的判断: view 填 看好/谨慎/回避; note 写逻辑(供复盘)
# 例: 半导体,看好,AI算力+国产替代持续
半导体,看好,
白酒,回避,长期走弱无反转
"""


def ensure_template():
    if not os.path.exists(VIEW_FILE):
        with open(VIEW_FILE, 'w', encoding='utf-8-sig') as f:
            f.write(TEMPLATE)
    return VIEW_FILE


def load_view():
    """读取人工观点 → {industry: {'view':..., 'note':...}}"""
    ensure_template()
    df = pd.read_csv(VIEW_FILE, encoding='utf-8-sig')
    df = df[df['industry'].notna() & ~df['industry'].astype(str).str.startswith('#')]
    out = {}
    for _, r in df.iterrows():
        ind = str(r['industry']).strip()
        if not ind or ind.startswith('#'):
            continue
        out[ind] = {'view': str(r.get('view', '')).strip(),
                    'note': str(r.get('note', '')).strip() if pd.notna(r.get('note')) else ''}
    return out


def _classify(view):
    """把自由文本 field 归一为 'bull' / 'bear' / 'neutral'。

    注意: 不能用 `'看好' in view` —— '不看好' 含子串 '看好', 会被误判为看好。
    故先判否定词, 再判肯定词。
    """
    v = str(view or '').strip()
    if ('不看好' in v) or ('回避' in v) or ('看空' in v) or ('谨慎' in v):
        return 'bear'
    if '看好' in v or '看多' in v:
        return 'bull'
    return 'neutral'


def bull_industries():
    """用户看好的行业列表"""
    v = load_view()
    return [ind for ind, x in v.items() if _classify(x['view']) == 'bull']


def bear_industries():
    """用户回避的行业列表"""
    v = load_view()
    return [ind for ind, x in v.items() if _classify(x['view']) == 'bear']


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    v = load_view()
    print(f'=== 我的观点 ({VIEW_FILE}) ===')
    if not v:
        print('  (空) 请编辑该文件填入你的判断')
        print(f'  格式: industry,view,note  (view: 看好/谨慎/回避)')
        return
    for ind, x in v.items():
        print(f'  {ind:14} [{x["view"]}] {x["note"]}')
    print(f'\n看好: {bull_industries()}')
    print(f'回避: {bear_industries()}')

    # 系统过滤: 看好 ∩ 不接盘(位置) ∩ 结构
    print('\n=== 系统对"看好行业"的过滤(位置/结构) ===')
    try:
        from src.utils.market_structure import load_industry_of
        from src.utils.ths_industry_rank import load_index
        from src.strategy.guardian import _industry_score, _industry_index, _load_prices, _ths_map
        for ind in bull_industries():
            idx = _industry_index(ind)
            sc = _industry_score(idx, None) if idx is not None else None
            if not sc:
                print(f'  {ind}: 无同花顺行业指数(名称需与同花顺一致)')
                continue
            if sc['距高点%'] > -3:
                verdict = '⚠ 高位(会接盘,等回调)'
            elif sc['距高点%'] < -35:
                verdict = '⚠ 深跌(接刀风险)'
            elif (sc.get('近20日%') or 0) >= 15:
                verdict = '⚠ 短期过热'
            else:
                verdict = '✓ 位置合适,可执行'
            print(f'  {ind:14} 距高点{sc["距高点%"]:+6.1f}% 近20日{sc["近20日%"]:+5.1f}% → {verdict}')
    except Exception as e:
        print(f'  [warn] {e}')
    print('\n分工: 方向由你定(上面的观点); 位置/结构由系统把关(不接盘/不接刀)')


if __name__ == '__main__':
    main()
