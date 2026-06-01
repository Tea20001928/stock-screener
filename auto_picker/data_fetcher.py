"""
自动选股 - 数据抓取模块
复用父模块的基础工具函数，实现三板竞价数据获取
"""

import sys
import os
import time
import pandas as pd
import akshare as ak
import requests
from datetime import datetime
from typing import Optional, Tuple, List, Dict

# 导入父模块的共享工具
if getattr(sys, 'frozen', False):
    sys.path.insert(0, sys._MEIPASS)
else:
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

    优先使用东方财富（akshare），失败则回退到新浪财经 API。

    返回 DataFrame，含 代码, 名称, 今开, 昨收, etc.
    运行条件：竞价结束后（9:25 之后）
    """
    # 策略1：东方财富（akshare）
    try:
        df = _retry(ak.stock_zh_a_spot_em)
        if df is not None and len(df) > 0:
            if "代码" in df.columns:
                df["代码"] = df["代码"].astype(str).str.zfill(6)
            return df
    except Exception:
        pass

    # 策略2：新浪财经 HTTP API（东方财富不可用时回退）
    try:
        df = _get_all_spot_sina()
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass

    return None


def get_spot_for_codes_sina(codes: List[str]) -> Dict[str, dict]:
    """
    通过新浪财经 API 批量获取指定股票的实时行情（轻量级，只拉候选股）

    codes: 股票代码列表，如 ['600000', '000001']
    返回: {code: {"name": str, "open": float, "prev_close": float}}

    新浪 API 格式: http://hq.sinajs.cn/list=sh600000,sz000001
    返回: var hq_str_sh600000="名称,今开,昨收,当前价,..."
    """
    if not codes:
        return {}

    # 构建新浪代码（沪深区分）
    sina_codes = []
    code_map = {}  # sina_code -> 6-digit code
    for code in codes:
        code = str(code).zfill(6)
        if code.startswith("6"):
            sc = f"sh{code}"
        else:
            sc = f"sz{code}"
        sina_codes.append(sc)
        code_map[sc] = code

    results = {}
    batch_size = 400  # 新浪单次请求上限约 800，保守取 400

    for i in range(0, len(sina_codes), batch_size):
        batch = sina_codes[i:i + batch_size]
        url = "http://hq.sinajs.cn/list=" + ",".join(batch)

        try:
            resp = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": "https://finance.sina.com.cn",
                },
            )
            resp.encoding = "gbk"

            for line in resp.text.strip().split("\n"):
                line = line.strip()
                if not line or "=" not in line:
                    continue

                # var hq_str_sh600000="name,open,prev_close,..."
                var_part, _, data_part = line.partition("=")
                data_part = data_part.strip().strip('"')
                if not data_part:
                    continue

                fields = data_part.split(",")
                if len(fields) < 3:
                    continue

                # 从变量名提取代码（hq_str_sh600000 → sh600000）
                var_name = var_part.split("_")[-1]
                original_code = code_map.get(var_name)
                if not original_code:
                    continue

                try:
                    results[original_code] = {
                        "name": fields[0],
                        "open": float(fields[1]) if fields[1] else 0.0,
                        "prev_close": float(fields[2]) if fields[2] else 0.0,
                    }
                except (ValueError, IndexError):
                    continue

        except Exception:
            # 单个批次失败不阻止整体，继续下一批
            continue

    return results


def _get_all_spot_sina() -> Optional[pd.DataFrame]:
    """
    通过新浪 API 获取全 A 股实时行情（作为东方财富不可用时的完整回退）
    返回 DataFrame，含 代码, 名称, 今开, 昨收 列
    """
    import requests as req

    # 沪深两市股票代码范围
    # 沪市主板: 600000-605999, 科创板: 688000-689999
    # 深市主板: 000001-004999, 中小板: 002000-004999, 创业板: 300000-301999
    all_codes = []
    # 沪市主板
    all_codes.extend([f"sh60{i:04d}" for i in range(0, 6000)])
    # 科创板（只取已有范围）
    all_codes.extend([f"sh688{i:03d}" for i in range(0, 700)])
    # 深市
    all_codes.extend([f"sz00{i:04d}" for i in range(1, 5000)])
    all_codes.extend([f"sz30{i:04d}" for i in range(0, 3000)])

    # 分批请求
    rows = []
    batch_size = 400
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://finance.sina.com.cn",
    }

    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i + batch_size]
        url = "http://hq.sinajs.cn/list=" + ",".join(batch)
        try:
            resp = req.get(url, timeout=15, headers=headers)
            resp.encoding = "gbk"
            for line in resp.text.strip().split("\n"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                var_part, _, data_part = line.partition("=")
                data_part = data_part.strip().strip('"')
                if not data_part:
                    continue
                fields = data_part.split(",")
                if len(fields) < 3 or not fields[1]:
                    # 跳过无开盘价的股票（停牌/未上市）
                    continue
                var_name = var_part.split("_")[-1]
                code = var_name[2:]  # 去掉 sh/sz 前缀
                try:
                    rows.append({
                        "代码": code.zfill(6),
                        "名称": fields[0],
                        "今开": float(fields[1]),
                        "昨收": float(fields[2]) if fields[2] else 0.0,
                    })
                except (ValueError, IndexError):
                    continue
        except Exception:
            continue

    if not rows:
        return None
    return pd.DataFrame(rows)


def get_today_auction_volume(symbol: str) -> Optional[float]:
    """
    获取当日集合竞价成交额（三板竞价金额）
    多策略：CDN trends2 → 东方财富 pre_min → Sina 首分钟

    symbol: 6位代码如 '000001'
    返回: 竞价成交额（元），失败返回 None
    """
    from data_fetcher import _get_auction_data_via_cdn, _get_auction_data_via_sina

    # 策略1：CDN trends2 接口（最可靠，含 9:15-9:25 竞价时段）
    result = _get_auction_data_via_cdn(symbol)
    if result is not None:
        return result.get("auction_amount")

    # 策略2：东方财富盘前分钟数据
    try:
        df = _retry(ak.stock_zh_a_hist_pre_min_em, symbol=symbol)
    except Exception:
        df = None

    if df is not None and len(df) > 0:
        amount = _parse_auction_from_df(df)
        if amount is not None:
            return amount

    # 策略3：新浪分钟数据首分钟成交额
    today_str = datetime.now().strftime("%Y-%m-%d")
    result = _get_auction_data_via_sina(symbol, today_str)
    if result is not None:
        return result.get("auction_amount")

    return None


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


def _parse_auction_from_df(df: pd.DataFrame) -> Optional[float]:
    """从分钟数据 DataFrame 中提取竞价时段成交额（9:15-9:25）"""
    time_col = None
    for col in df.columns:
        col_lower = str(col).lower()
        if "时间" in col_lower or "time" in col_lower:
            time_col = col
            break

    if time_col is None:
        return None

    time_series = df[time_col].astype(str)
    auction_mask = time_series.str.contains(r"09:1[5-9]|09:2[0-5]", na=False)
    auction_rows = df[auction_mask]

    if len(auction_rows) == 0:
        return None

    amount_col = None
    for col in ["成交额", "成交金额"]:
        if col in auction_rows.columns:
            amount_col = col
            break

    if amount_col is None:
        return None

    total = float(auction_rows[amount_col].sum())
    return total if total > 0 else None
