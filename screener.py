"""
筛选模块 - 连板股筛选核心逻辑
"""

from datetime import datetime
from typing import List, Tuple, Optional, Callable

from data_fetcher import (
    get_recent_trading_days,
    get_latest_trading_day,
    fetch_all_data,
)


def determine_target_dates() -> Tuple[str, str, bool]:
    """
    确定目标交易日（二板日 和 一板日）

    规则：
    - 如果在交易日运行：二板=今天，一板=上一个交易日
    - 如果在非交易日运行：二板=最近交易日，一板=上一个交易日
    - 如果在9:30之前运行（盘中数据不完整），也使用最近完整交易日

    返回: (二板日期, 一板日期, 是否为最近交易日)
      日期格式: "YYYY-MM-DD"
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # 获取最近两个交易日
    recent_days = get_recent_trading_days(5)

    # 判断今天是否为交易日
    is_trading_day = today_str in recent_days

    # 判断当前时间是否在盘后（15:30之后数据才稳定）
    is_after_close = now.hour >= 15 and now.minute >= 30

    if is_trading_day and is_after_close:
        # 交易日盘后 → 当天数据可用
        current_date = today_str
        is_latest = True
        # 一板 = 上一个交易日
        today_index = recent_days.index(today_str)
        prev_date = recent_days[today_index + 1] if today_index + 1 < len(recent_days) else recent_days[-1]
    elif is_trading_day and not is_after_close:
        # 交易日但盘中 → 用上一个交易日作为"当天"
        current_date = recent_days[1] if len(recent_days) > 1 else recent_days[0]
        is_latest = (current_date == recent_days[0])
        today_index = recent_days.index(current_date)
        prev_date = recent_days[today_index + 1] if today_index + 1 < len(recent_days) else recent_days[-1]
    else:
        # 非交易日 → 最近交易日作为二板
        current_date = recent_days[0]
        is_latest = True
        prev_date = recent_days[1] if len(recent_days) > 1 else recent_days[0]

    return current_date, prev_date, is_latest


def screen_consecutive_limit_up(
    progress_callback: Optional[Callable] = None,
) -> Tuple[List[dict], str, str]:
    """
    主筛选函数：筛选连续两天涨停的股票

    参数:
        progress_callback: 可选进度回调 (msg: str, pct: float)

    返回:
        (股票数据列表, 二板日期, 一板日期)
        列表每项为 dict，键与 config.COLUMNS 一致
    """
    # 确定目标日期
    current_date, prev_date, is_latest = determine_target_dates()

    # 获取数据并筛选
    enriched, current_zt, prev_zt = fetch_all_data(
        current_date=current_date,
        prev_date=prev_date,
        is_latest=is_latest,
        progress_callback=progress_callback,
    )

    return enriched, current_date, prev_date
