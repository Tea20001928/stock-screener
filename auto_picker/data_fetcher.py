"""
自动选股 - 数据抓取模块
复用父模块的基础工具函数，实现三板竞价数据获取
"""

import sys
import os
import time
import pandas as pd
import akshare as ak
from typing import Optional, Tuple, List

# 导入父模块的共享工具
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_fetcher import (
    _retry,
    _code_to_market,
    _format_limit_up_time,
    get_recent_trading_days,
    get_latest_trading_day,
    get_limit_up_stocks,
    get_daily_bar,
)
from auto_picker.config import REQUEST_TIMEOUT, MAX_RETRIES


def get_today_spot_data() -> Optional[pd.DataFrame]:
    """
    获取当日全A股实时行情快照（用于三板竞价数据）
    返回 DataFrame，含 代码, 名称, 今开, 昨收, etc.
    运行条件：竞价结束后（9:25 之后）
    """
    try:
        df = _retry(ak.stock_zh_a_spot_em)
    except Exception:
        return None

    if df is None or len(df) == 0:
        return None

    # 标准化代码
    if "代码" in df.columns:
        df["代码"] = df["代码"].astype(str).str.zfill(6)

    return df


def get_today_auction_volume(symbol: str) -> Optional[float]:
    """
    获取当日集合竞价成交额（三板竞价金额）
    使用盘前分钟数据，过滤 9:15-9:25 时段

    symbol: 6位代码如 '000001'
    返回: 竞价成交额（元），失败返回 None
    """
    try:
        df = _retry(ak.stock_zh_a_hist_pre_min_em, symbol=symbol)
    except Exception:
        return None

    if df is None or len(df) == 0:
        return None

    # 找时间列
    time_col = None
    for col in df.columns:
        col_lower = str(col).lower()
        if "时间" in col_lower or "time" in col_lower:
            time_col = col
            break

    if time_col is None:
        return None

    # 过滤集合竞价时段
    time_series = df[time_col].astype(str)
    auction_mask = time_series.str.contains(r"09:1[5-9]|09:2[0-5]", na=False)
    auction_rows = df[auction_mask]

    if len(auction_rows) == 0:
        return None

    # 找成交额列
    amount_col = None
    for col in ["成交额", "成交金额"]:
        if col in auction_rows.columns:
            amount_col = col
            break

    if amount_col is None:
        return None

    return float(auction_rows[amount_col].sum())


def get_auction_price_change(symbol: str, date_str: str, prev_date_str: str) -> Optional[float]:
    """
    计算某日的竞价涨幅 = (当日开盘价 - 前日收盘价) / 前日收盘价 × 100%

    symbol: 股票代码
    date_str: 目标日期
    prev_date_str: 目标日期的前一交易日（用于获取昨收）

    返回: 竞价涨幅百分比，失败返回 None
    """
    bar = get_daily_bar(symbol, date_str, prev_date_str=prev_date_str)
    if bar is None:
        return None

    open_price = bar.get("open", 0)
    prev_close = bar.get("prev_close", 0)

    if prev_close <= 0 or open_price <= 0:
        return None

    return round((open_price - prev_close) / prev_close * 100, 2)


def get_stock_free_float_cap(symbol: str, date_str: str) -> Optional[float]:
    """
    获取个股在某日的自由流通市值
    从涨停股池数据中提取，如果没有则从日线数据获取

    返回: 流通市值（元）或 None
    """
    date_compact = date_str.replace("-", "")
    try:
        zt_df = get_limit_up_stocks(date_str)
        if not zt_df.empty and "代码" in zt_df.columns:
            row = zt_df[zt_df["代码"] == symbol]
            if len(row) > 0 and "流通市值" in row.columns:
                val = row.iloc[0]["流通市值"]
                if pd.notna(val):
                    return float(val)
    except Exception:
        pass

    return None
