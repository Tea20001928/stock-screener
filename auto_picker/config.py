"""
自动选股 - 配置文件
运行时间：交易日 9:25 竞价结束后
命名规则：三板=当天, 二板=前一交易日, 一板=再前一交易日
"""

import os

# 输出文件夹
OUTPUT_DIR_NAME = "连扳股复盘"
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
OUTPUT_DIR = os.path.join(DESKTOP_PATH, OUTPUT_DIR_NAME)

# Excel 表头（自动选股）
COLUMNS = [
    "股票代码",
    "股票名称",
    "行业涨停数",  # 二板日该行业板块涨停股总数
    "三板竞价涨幅",
    "三板竞价金额",
    "二板竞价涨幅",
    "二板竞价金额",
    "二板自由流通市值",
    "指标1:三板/二板竞价金额",
    "指标2:竞流比(%)",
    "二板最后涨停时间",
    "行业",
    "评级",
]

# === 筛选阈值 ===

# 指标1: 三板竞价金额 / 二板竞价金额
RATIO1_PREFERRED = 1.3   # > 1.3 优选(绿)
RATIO1_QUALIFIED = 1.0   # 1.0-1.3 合格(黄), < 1.0 不合格(红)

# 指标2: 竞流比 = 三板竞价金额 / 二板自由流通市值
# 流通盘分档阈值（亿元）
FLOAT_LV1 = 60   # < 60亿
FLOAT_LV2 = 100  # 60-100亿
FLOAT_LV3 = 200  # 100-200亿

# 竞流比合格线（根据流通盘分档）
JINGLIU_QUALIFIED = {
    "small": 1.7,    # 流通盘 < 60亿: > 1.7% 合格
    "mid_low": 1.3,  # 60-100亿: > 1.3% 合格
    "mid_high": 1.0, # 100-200亿: > 1.0% 合格
    "large": 1.0,    # > 200亿: > 1.0% 合格
}

JINGLIU_PREFERRED = 2.0  # 所有档位: > 2% 优选

# 基础门槛
# 三板竞价涨幅 > 二板竞价涨幅
# 三板竞价金额 > 二板竞价金额

# 请求配置
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# 颜色定义（用于 Excel）
COLOR_GREEN = "92D050"   # 优选
COLOR_YELLOW = "FFC000"  # 合格
COLOR_RED = "FF6B6B"     # 不合格
COLOR_GREY = "C0C0C0"    # 不达标
