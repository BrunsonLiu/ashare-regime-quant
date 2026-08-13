"""
supply_chain.py - A股产业链主题映射表

核心理念（散户信息差优势）：
  当一个主题被爆炒到高位时，资金会沿产业链向上游扩散。
  上游资源股（铜/铝/稀土等）往往还在低位，且几乎全在主板（60/00），
  与我们的主板股票池天然契合——这正是散户能提前埋伏的地方。

数据结构：
  THEME_CHAIN = {
      主题名: {
          "trigger": 主题爆发的催化逻辑（为什么这条链会起来）,
          "stages": [  # 按产业链位置从下游到上游排列
              {
                  "name": 环节名,
                  "position": "downstream|midstream|upstream",  # 下游=先炒, 上游=后炒
                  "note": 该环节的角色说明,
                  "stocks": [  # 标的，主板优先
                      {"code": "601899", "name": "紫金矿业", "board": "主板"},
                      ...
                  ]
              },
              ...
          ]
      }
  }

使用方式：
  1. 主题爆发 → 识别哪些环节已经高位（下游/中游）
  2. 找还没炒的上游环节 → 候选埋伏标的
  3. 用 LurkDetector 做低位确认 → 买入
"""

# ==================== 产业链主题映射 ====================

THEME_CHAIN = {
    "AI算力": {
        "trigger": "AI大模型爆发 → 算力需求激增 → 数据中心/服务器扩建 → 上游原材料缺口",
        "stages": [
            {
                "name": "光模块",
                "position": "downstream",
                "note": "算力最直接受益，最先炒，已高位",
                "stocks": [
                    {"code": "300308", "name": "中际旭创", "board": "创业板"},
                ],
            },
            {
                "name": "PCB/覆铜板",
                "position": "midstream",
                "note": "服务器/交换机基板，中游",
                "stocks": [
                    {"code": "002463", "name": "沪电股份", "board": "主板"},
                    {"code": "002916", "name": "深南电路", "board": "主板"},
                    {"code": "600183", "name": "生益科技", "board": "主板"},
                ],
            },
            {
                "name": "高速铜缆/连接器",
                "position": "midstream",
                "note": "GPU互联的铜连接方案，中游",
                "stocks": [
                    {"code": "002130", "name": "沃尔核材", "board": "主板"},
                    {"code": "300563", "name": "神宇股份", "board": "创业板"},
                ],
            },
            {
                "name": "液冷散热",
                "position": "midstream",
                "note": "高功耗服务器的散热刚需",
                "stocks": [
                    {"code": "002837", "name": "英维克", "board": "主板"},
                ],
            },
            {
                "name": "铜（工业金属）",
                "position": "upstream",
                "note": "铜缆/连接器/散热/线缆全都要铜，上游且多低位",
                "stocks": [
                    {"code": "601899", "name": "紫金矿业", "board": "主板"},
                    {"code": "600362", "name": "江西铜业", "board": "主板"},
                    {"code": "000630", "name": "铜陵有色", "board": "主板"},
                    {"code": "000878", "name": "云南铜业", "board": "主板"},
                    {"code": "601168", "name": "西部矿业", "board": "主板"},
                ],
            },
            {
                "name": "铝（散热/结构件）",
                "position": "upstream",
                "note": "服务器结构件/散热片用铝，上游",
                "stocks": [
                    {"code": "600219", "name": "南山铝业", "board": "主板"},
                    {"code": "601677", "name": "明泰铝业", "board": "主板"},
                ],
            },
            {
                "name": "电力",
                "position": "upstream",
                "note": "算力中心耗电巨大，电力是隐藏上游",
                "stocks": [
                    {"code": "600011", "name": "华能国际", "board": "主板"},
                    {"code": "600795", "name": "国电电力", "board": "主板"},
                    {"code": "600900", "name": "长江电力", "board": "主板"},
                ],
            },
        ],
    },

    "人形机器人": {
        "trigger": "AI具身智能 → 人形机器人量产预期 → 减速器/电机/丝杠 → 上游金属/稀土",
        "stages": [
            {
                "name": "减速器",
                "position": "downstream",
                "note": "机器人关节核心，最先炒，已高位",
                "stocks": [
                    {"code": "002472", "name": "双环传动", "board": "主板"},
                ],
            },
            {
                "name": "丝杠/轴承",
                "position": "midstream",
                "note": "直线传动部件，中游",
                "stocks": [
                    {"code": "603667", "name": "五洲新春", "board": "主板"},
                ],
            },
            {
                "name": "电机/电驱",
                "position": "midstream",
                "note": "关节电机，中游",
                "stocks": [
                    {"code": "603728", "name": "鸣志电器", "board": "主板"},
                    {"code": "600580", "name": "卧龙电驱", "board": "主板"},
                ],
            },
            {
                "name": "铜/铝合金",
                "position": "upstream",
                "note": "机器人骨架/线束用铜铝，上游低位",
                "stocks": [
                    {"code": "000878", "name": "云南铜业", "board": "主板"},
                    {"code": "600219", "name": "南山铝业", "board": "主板"},
                ],
            },
            {
                "name": "稀土永磁",
                "position": "upstream",
                "note": "伺服电机必用钕铁硼磁材，上游核心",
                "stocks": [
                    {"code": "000970", "name": "中科三环", "board": "主板"},
                    {"code": "600366", "name": "宁波韵升", "board": "主板"},
                    {"code": "600111", "name": "北方稀土", "board": "主板"},
                ],
            },
        ],
    },

    "新能源车/储能": {
        "trigger": "新能源车渗透率提升 + 储能爆发 → 电池产能扩张 → 铜铝需求持续",
        "stages": [
            {
                "name": "动力电池",
                "position": "downstream",
                "note": "最直接，已充分定价",
                "stocks": [
                    {"code": "300750", "name": "宁德时代", "board": "创业板"},
                ],
            },
            {
                "name": "整车",
                "position": "downstream",
                "note": "整车，周期内波动",
                "stocks": [
                    {"code": "601127", "name": "赛力斯", "board": "主板"},
                ],
            },
            {
                "name": "铜（导线/电机）",
                "position": "upstream",
                "note": "单车用铜量是燃油车3-4倍，上游刚需",
                "stocks": [
                    {"code": "000630", "name": "铜陵有色", "board": "主板"},
                    {"code": "601168", "name": "西部矿业", "board": "主板"},
                    {"code": "603993", "name": "洛阳钼业", "board": "主板"},
                ],
            },
            {
                "name": "铝（轻量化）",
                "position": "upstream",
                "note": "车身轻量化用铝，上游",
                "stocks": [
                    {"code": "000807", "name": "云铝股份", "board": "主板"},
                    {"code": "601600", "name": "中国铝业", "board": "主板"},
                    {"code": "601677", "name": "明泰铝业", "board": "主板"},
                ],
            },
        ],
    },

    "半导体国产替代": {
        "trigger": "中美科技博弈 → 国产替代加速 → 设备/材料/上游金属",
        "stages": [
            {
                "name": "芯片设计",
                "position": "downstream",
                "note": "设计端，已高位",
                "stocks": [
                    {"code": "688256", "name": "寒武纪", "board": "科创板"},
                ],
            },
            {
                "name": "半导体设备",
                "position": "midstream",
                "note": "晶圆厂扩产核心设备，中游",
                "stocks": [
                    {"code": "002371", "name": "北方华创", "board": "主板"},
                ],
            },
            {
                "name": "半导体材料",
                "position": "midstream",
                "note": "光刻胶/靶材/气体，中游",
                "stocks": [
                    {"code": "600206", "name": "有研新材", "board": "主板"},
                    {"code": "000969", "name": "安泰科技", "board": "主板"},
                ],
            },
            {
                "name": "稀有金属（靶材原料）",
                "position": "upstream",
                "note": "溅射靶材用高纯金属，上游",
                "stocks": [
                    {"code": "000969", "name": "安泰科技", "board": "主板"},
                    {"code": "600206", "name": "有研新材", "board": "主板"},
                ],
            },
        ],
    },

    "军工/航空": {
        "trigger": "国防开支增长 + 航空发动机突破 → 高温合金/钛材需求",
        "stages": [
            {
                "name": "主机厂",
                "position": "downstream",
                "note": "整机，已充分定价",
                "stocks": [
                    {"code": "600760", "name": "中航沈飞", "board": "主板"},
                ],
            },
            {
                "name": "高温合金",
                "position": "upstream",
                "note": "发动机热端部件必用，上游核心",
                "stocks": [
                    {"code": "600399", "name": "抚顺特钢", "board": "主板"},
                ],
            },
            {
                "name": "钛材",
                "position": "upstream",
                "note": "航空结构件用钛，上游",
                "stocks": [
                    {"code": "600456", "name": "宝钛股份", "board": "主板"},
                    {"code": "002149", "name": "西部材料", "board": "主板"},
                ],
            },
        ],
    },

    "低空经济/飞行汽车": {
        "trigger": "低空经济政策放开 → eVTOL量产 → 轻量化材料需求",
        "stages": [
            {
                "name": "整机/eVTOL",
                "position": "downstream",
                "note": "整机，概念炒作为主",
                "stocks": [
                    {"code": "600038", "name": "中直股份", "board": "主板"},
                ],
            },
            {
                "name": "电机/电驱",
                "position": "midstream",
                "note": "eVTOL动力系统，中游",
                "stocks": [
                    {"code": "600580", "name": "卧龙电驱", "board": "主板"},
                    {"code": "603308", "name": "应流股份", "board": "主板"},
                ],
            },
            {
                "name": "轻量化铝",
                "position": "upstream",
                "note": "飞行器轻量化用铝，上游",
                "stocks": [
                    {"code": "000807", "name": "云铝股份", "board": "主板"},
                    {"code": "601600", "name": "中国铝业", "board": "主板"},
                ],
            },
        ],
    },
}


# ==================== 防御性板块（GJD稳定器，无赚钱效应）====================
# 这些板块基本面再好也不参与博弈，是"稳定市场工具"
DEFENSIVE_SECTORS = {
    "酿酒", "白酒", "银行", "保险", "电力", "公用事业",
    "石油", "煤炭", "钢铁", "铁路", "高速公路",
}


# ==================== 工具函数 ====================

def get_upstream_stocks(theme: str, board_filter=None) -> list:
    """
    获取某主题的上游（埋伏）标的
    board_filter: None=全部, ["60","00"]=只主板
    """
    if theme not in THEME_CHAIN:
        return []
    result = []
    for stage in THEME_CHAIN[theme]["stages"]:
        if stage["position"] != "upstream":
            continue
        for s in stage["stocks"]:
            if board_filter is None or any(s["code"].startswith(b) for b in board_filter):
                result.append({
                    "code": s["code"],
                    "name": s["name"],
                    "stage": stage["name"],
                    "theme": theme,
                    "board": s["board"],
                })
    return result


def get_all_upstream_stocks(board_filter=("60", "00")) -> list:
    """获取所有主题的上游标的（去重）"""
    seen = {}
    for theme in THEME_CHAIN:
        for s in get_upstream_stocks(theme, board_filter):
            code = s["code"]
            if code not in seen:
                seen[code] = s
            else:
                # 同一只票出现在多个主题 → 记录多主题
                if "themes" not in seen[code]:
                    seen[code]["themes"] = [seen[code]["theme"]]
                seen[code]["themes"].append(theme)
    return list(seen.values())


def get_theme_by_code(code: str) -> list:
    """反查某只股票属于哪些主题"""
    themes = []
    for theme, data in THEME_CHAIN.items():
        for stage in data["stages"]:
            for s in stage["stocks"]:
                if s["code"] == code:
                    themes.append({"theme": theme, "stage": stage["name"],
                                   "position": stage["position"]})
    return themes


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("=== 产业链主题总览 ===")
    for theme, data in THEME_CHAIN.items():
        stages = data["stages"]
        up = [s["name"] for s in stages if s["position"] == "upstream"]
        print(f"\n【{theme}】")
        print(f"  催化: {data['trigger'][:40]}...")
        print(f"  环节: {' → '.join(s['name'] for s in stages)}")
        print(f"  上游埋伏: {', '.join(up)}")

    print("\n\n=== 全部上游标的（主板）===")
    stocks = get_all_upstream_stocks(("60", "00"))
    print(f"共 {len(stocks)} 只去重标的")
    for s in stocks:
        themes = s.get("themes", [s["theme"]])
        print(f"  {s['code']} {s['name']} [{s['stage']}] 主题={','.join(themes)}")
