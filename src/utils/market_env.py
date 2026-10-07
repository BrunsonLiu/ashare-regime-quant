# -*- coding: utf-8 -*-
"""
四环境分类 —— 守则第一章的代码化
====================================
守则: A股有且只有四种环境, 判断错了后面全错。
  A 主线行情(赚钱环境): 有明确板块持续领涨, 涨停家数多, 连板高度起来
  B 主线散乱(绞肉环境): 无持续主线, 涨停少, 热点一天一换 → 最危险
  C 超跌反弹(短线环境): 连续急跌, 情绪恐慌, 缩量止跌
  D 熊市/空头(休息环境): MA20<MA60 且近20日跌>4% → 空仓最好

数据来源: 指数(均线/涨跌幅) + 情绪数据(涨停家数/连板高度/炸板率)
—— 情绪数据正是"主线凝聚度"的直接度量, 这是它真正的用途。

全部离线可复现, 无前视(用 T-1 及之前的数据判 T 日环境)。
"""
import numpy as np
import pandas as pd


# 环境常量
ENV_A = 'A'  # 主线行情
ENV_B = 'B'  # 主线散乱
ENV_C = 'C'  # 超跌反弹
ENV_D = 'D'  # 熊市空头

ENV_DESC = {
    ENV_A: '主线行情: 有明确主线+连板高度, 追龙头/持有',
    ENV_B: '主线散乱: 无持续主线, 轻仓或空仓, 休息最好',
    ENV_C: '超跌反弹: 连续急跌后企稳, 轻仓快进快出',
    ENV_D: '熊市空头: 均线空头排列, 空仓观望',
}

# 环境 → 目标仓位上限(守则第五章)
ENV_EXPOSURE = {
    ENV_A: 0.80,
    ENV_B: 0.20,
    ENV_C: 0.30,
    ENV_D: 0.00,
}


class MarketEnvironment:
    """四环境分类器(守则第一章)"""

    def __init__(self, cfg=None):
        cfg = cfg or {}
        # 主线行情阈值(情绪数据)
        self.zt_main = cfg.get('zt_main', 50)        # 涨停家数>50 = 有赚钱效应
        self.lb_main = cfg.get('lb_main', 3)          # 连板高度≥3 = 主线凝聚
        self.zt_dead = cfg.get('zt_dead', 30)         # 涨停<30 = 散乱
        # 熊市
        self.ma_short, self.ma_long = 20, 60
        self.bear_drop = cfg.get('bear_drop', -0.04)  # 近20日跌>4%
        # 超跌
        self.crash_5d = cfg.get('crash_5d', -0.05)    # 5日跌>5% = 急跌
        self.panic_zhaban = cfg.get('panic_zhaban', 0.45)  # 炸板率>45% = 恐慌

    def classify_series(self, index_df, sentiment_df):
        """
        返回 {date: env} 以及诊断列, date 为 pd.Timestamp。
        sentiment_df: [date, zt_count, lianban_height, zhaban_rate]
        用 T-1 及之前数据判 T 日环境(shift(1), 无前视)。
        """
        idx = index_df.sort_values('date').reset_index(drop=True).copy()
        idx['date'] = pd.to_datetime(idx['date'])
        close = idx['close']
        ma_s = close.rolling(self.ma_short).mean()
        ma_l = close.rolling(self.ma_long).mean()
        ret20 = close.pct_change(20)
        ret5 = close.pct_change(5)

        s = sentiment_df.copy()
        s['date'] = pd.to_datetime(s['date'])
        s = s.sort_values('date')

        df = idx[['date']].copy()
        df['close'] = close.values
        df['ma_s'] = ma_s.values
        df['ma_l'] = ma_l.values
        df['ret20'] = ret20.values
        df['ret5'] = ret5.values
        df = df.merge(s[['date', 'zt_count', 'lianban_height', 'zhaban_rate']],
                      on='date', how='left')

        # 无前视: 判 T 日用 T-1 数据
        for c in ('ma_s', 'ma_l', 'ret20', 'ret5', 'zt_count', 'lianban_height', 'zhaban_rate'):
            df[c] = df[c].shift(1)

        envs, diags = [], []
        for _, r in df.iterrows():
            if pd.isna(r['ma_l']) or pd.isna(r['zt_count']):
                envs.append('WARMUP'); diags.append({}); continue
            env, why = self._classify_row(r)
            envs.append(env); diags.append(why)
        df['env'] = envs
        df['why'] = diags
        return dict(zip(df['date'], df['env'])), df

    def _classify_row(self, r):
        """单行判定, 优先级: D(安全) > A(主线) > C(超跌) > B(默认)"""
        # D 熊市: 均线空头 + 近20日深跌 —— 最高优先级(保存实力)
        if r['ma_s'] < r['ma_l'] * 0.98 and r['ret20'] < self.bear_drop:
            return ENV_D, 'MA20<MA60且20日深跌'
        # A 主线行情: 涨停多 + 有连板高度 = 主线凝聚, 赚钱效应
        if r['zt_count'] >= self.zt_main and r['lianban_height'] >= self.lb_main:
            return ENV_A, f"涨停{int(r['zt_count'])}≥{self.zt_main}且高度{int(r['lianban_height'])}"
        # C 超跌反弹: 指数急跌 或 情绪极度恐慌
        crash = r['ret5'] < self.crash_5d
        panic = (not pd.isna(r['zhaban_rate'])) and r['zhaban_rate'] > self.panic_zhaban
        if crash or panic:
            return ENV_C, ('5日急跌' if crash else '炸板率恐慌')
        # B 主线散乱: 默认(涨停少, 无明确主线)
        return ENV_B, f"涨停{int(r['zt_count'])}<{self.zt_main}无主线"

    def classify(self, date, index_df, sentiment_df):
        """单日分类(便捷入口); 批量场景请用 classify_series"""
        envs, _ = self.classify_series(index_df, sentiment_df)
        return envs.get(pd.Timestamp(date), 'WARMUP')


def hysteresis_confirm(env_series, enter_n=3, exit_n=2, target='A'):
    """
    环境滞后确认 —— 守则原文:"板块持续领涨3天以上→主线确认"。
    连续 enter_n 天为 target 环境才确认进入; 连续 exit_n 天非 target 才确认退出。
    目的: 环境短脉冲会造成高频翻转(实测3.5年219次, 成本拖累约66%),
    滞后确认把翻转降到可控水平(守则口径3/2 → 58次, 拖累约17%)。

    env_series: {date: env} 或 Series
    返回: 与输入同型的 {date: bool}(是否处于确认后的 target 环境)
    """
    s = pd.Series(env_series).sort_index()
    confirmed = False
    a_cnt = nona_cnt = 0
    out = {}
    for d, v in s.items():
        if v == target:
            a_cnt += 1
            nona_cnt = 0
            if not confirmed and a_cnt >= enter_n:
                confirmed = True
        else:
            nona_cnt += 1
            a_cnt = 0
            if confirmed and nona_cnt >= exit_n:
                confirmed = False
        out[d] = confirmed
    return pd.Series(out)


def load_sentiment():
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    s = pd.read_csv(os.path.join(root, 'data', 'sentiment_3y.csv'))
    s['date'] = pd.to_datetime(s['date'])
    return s
