"""
自动选股 - 筛选逻辑
三板=当天（竞价结束），二板=前一交易日，一板=再前一交易日
筛选二板+一板都涨停的股票，用三板竞价数据评分
"""

import sys
import os
import time
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Callable, Tuple
from collections import OrderedDict

if getattr(sys, 'frozen', False):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_fetcher import (
    get_recent_trading_days,
    get_limit_up_stocks,
    get_industry_limit_up_count,
)
from auto_picker.data_fetcher import (
    get_today_spot_data,
    get_spot_for_codes_sina,
    get_today_auction_volume,
    get_auction_price_change,
)
from auto_picker.config import (
    COLUMNS,
    RATIO1_PREFERRED,
    RATIO1_QUALIFIED,
    JINGLIU_QUALIFIED,
    JINGLIU_PREFERRED,
    FLOAT_LV1,
    FLOAT_LV2,
    FLOAT_LV3,
    COLOR_GREEN,
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_GREY,
)


def _get_jingliu_qualified_threshold(free_float_cap: float) -> float:
    """
    根据流通市值获取竞流比合格线（%）
    free_float_cap: 流通市值（元）
    """
    yi = free_float_cap / 1e8  # 转为亿元
    if yi < FLOAT_LV1:
        return JINGLIU_QUALIFIED["small"]
    elif yi < FLOAT_LV2:
        return JINGLIU_QUALIFIED["mid_low"]
    elif yi < FLOAT_LV3:
        return JINGLIU_QUALIFIED["mid_high"]
    else:
        return JINGLIU_QUALIFIED["large"]


def _rate_indicator1(ratio: float) -> Tuple[str, str]:
    """
    指标1评级：三板竞价金额 / 二板竞价金额
    返回: (评级, 颜色代码)
    """
    if ratio > RATIO1_PREFERRED:
        return "优选", COLOR_GREEN
    elif ratio >= RATIO1_QUALIFIED:
        return "合格", COLOR_YELLOW
    else:
        return "不合格", COLOR_RED


def _rate_indicator2(jingliu: float, free_float_cap: float) -> Tuple[str, str]:
    """
    指标2评级：竞流比 = 三板竞价金额 / 二板自由流通市值 × 100%
    返回: (评级, 颜色代码)
    """
    if jingliu > JINGLIU_PREFERRED:
        return "优选", COLOR_GREEN

    threshold = _get_jingliu_qualified_threshold(free_float_cap)
    if jingliu > threshold:
        return "合格", COLOR_YELLOW
    else:
        return "不合格", COLOR_RED


def _overall_rating(r1: str, r2: str, basic_ok: bool) -> Tuple[str, str]:
    """
    综合评级
    basic_ok: 是否通过基础门槛（三板竞价涨幅>二板竞价涨幅 AND 三板竞价金额>二板竞价金额）
    """
    if not basic_ok:
        return "不达标", COLOR_GREY

    ratings = [r1, r2]
    if "不合格" in ratings:
        return "不合格", COLOR_RED
    if "优选" in ratings:
        return "优选", COLOR_GREEN
    return "合格", COLOR_YELLOW


def screen_auto_pick(
    progress_callback: Optional[Callable] = None,
) -> Tuple[List[dict], str, str, str]:
    """
    自动选股主函数

    返回: (股票数据列表, 三板日期, 二板日期, 一板日期)
    """
    # 0. 交易日校验 — 非交易日禁止运行
    today_str = datetime.now().strftime("%Y-%m-%d")
    recent_days = get_recent_trading_days(10)
    if len(recent_days) < 4:
        raise ValueError("交易日历数据不足")

    if today_str != recent_days[0]:
        raise ValueError(
            f"今天是 {today_str}，不是交易日！\n"
            f"最近交易日为 {recent_days[0]}。\n"
            f"自动选股功能只能在交易日 9:25 竞价结束后运行。"
        )

    # 1. 确定三个日期
    if progress_callback:
        progress_callback("获取交易日历...", 0.05)

    sanban_date = recent_days[0]   # 三板=今天
    erban_date = recent_days[1]    # 二板=昨交易日
    yiban_date = recent_days[2]    # 一板=前交易日
    # 一板的前一交易日（用于计算一板昨收）
    yiban_prev = recent_days[3]

    if progress_callback:
        progress_callback(
            f"三板={sanban_date}, 二板={erban_date}, 一板={yiban_date}", 0.08
        )

    # 2. 先获取二板+一板涨停股，确定候选范围（避免全市场扫 5000+ 只股票）
    if progress_callback:
        progress_callback(f"获取 {erban_date} 涨停股列表...", 0.12)

    erban_zt = get_limit_up_stocks(erban_date)
    if erban_zt.empty:
        raise ValueError(f"{erban_date} 无涨停数据")

    if progress_callback:
        progress_callback(f"获取 {yiban_date} 涨停股列表...", 0.2)

    yiban_zt = get_limit_up_stocks(yiban_date)
    if yiban_zt.empty:
        raise ValueError(f"{yiban_date} 无涨停数据")

    # 统计二板日各行业的涨停股数量（选股模式用前一天行业涨停数）
    industry_counts = get_industry_limit_up_count(erban_zt)

    # 交集 → 连板候选股
    if progress_callback:
        progress_callback("筛选一板+二板连板股...", 0.25)

    erban_codes = set(erban_zt["代码"].tolist())
    yiban_codes = set(yiban_zt["代码"].tolist())
    candidates = erban_codes & yiban_codes

    if not candidates:
        raise ValueError(f"未找到 {yiban_date} 和 {erban_date} 连续涨停的股票")

    candidates_sorted = sorted(candidates)

    # 构建二板和一板数据索引
    erban_index = {}
    for _, row in erban_zt.iterrows():
        erban_index[str(row["代码"]).zfill(6)] = row

    yiban_index = {}
    for _, row in yiban_zt.iterrows():
        yiban_index[str(row["代码"]).zfill(6)] = row

    # 3. 获取实时行情 — 只拉候选股，先试东方财富，失败回退新浪
    if progress_callback:
        progress_callback(f"获取 {len(candidates_sorted)} 只候选股实时行情...", 0.28)

    spot_data = _fetch_candidate_spot_data(candidates_sorted)

    # 4. 逐只股票分析
    total = len(candidates_sorted)
    results = []

    for i, code in enumerate(candidates_sorted):
        if progress_callback:
            progress_callback(
                f"分析股票 ({i+1}/{total}): {code}",
                0.35 + (0.55 * (i + 1) / total),
            )

        er_row = erban_index.get(code)
        yb_row = yiban_index.get(code)
        spot = spot_data.get(code)  # None 表示未获取到行情（可能停牌）

        name = er_row["名称"] if er_row is not None else (
            spot["name"] if spot else code
        )

        # ---- 三板竞价数据 ----
        sanban_open = spot["open"] if spot else 0
        sanban_prev_close = spot["prev_close"] if spot else 0
        sanban_jia_change = None
        if sanban_prev_close > 0 and sanban_open > 0:
            sanban_jia_change = round(
                (sanban_open - sanban_prev_close) / sanban_prev_close * 100, 2
            )

        # 三板竞价金额（今日集合竞价成交额）
        sanban_auction_amount = get_today_auction_volume(code)

        # ---- 二板竞价数据 ----
        erban_jia_change = get_auction_price_change(code, erban_date, yiban_date)
        # 二板竞价金额（使用 pre_min + 分钟数据）
        erban_auction_vol = _get_auction_amount_for_date(code, erban_date)

        # ---- 基础字段 ----
        from data_fetcher import get_free_float_cap
        fallback_float = (
            float(er_row["流通市值"]) if er_row is not None and pd.notna(er_row.get("流通市值")) else 0
        )
        free_float_cap = get_free_float_cap(code, fallback=fallback_float) if fallback_float > 0 else 0
        last_zt_time = er_row.get("最后封板时间", "N/A") if er_row is not None else "N/A"
        industry = er_row.get("所属行业", "N/A") if er_row is not None else "N/A"
        industry_zt_count = industry_counts.get(industry, 0) if industry != "N/A" else 0

        # 格式化涨停时间
        from data_fetcher import _format_limit_up_time
        last_zt_time = _format_limit_up_time(last_zt_time)

        # ---- 基础门槛检查 ----
        basic_pass = True
        if sanban_jia_change is None or erban_jia_change is None:
            basic_pass = False
        elif sanban_jia_change <= erban_jia_change:
            basic_pass = False
        if sanban_auction_amount is None or erban_auction_vol is None:
            basic_pass = False
        elif sanban_auction_amount <= erban_auction_vol:
            basic_pass = False

        # ---- 指标1: 三板/二板竞价金额 ----
        ratio1 = None
        r1_rating = "不达标"
        r1_color = COLOR_GREY
        if (
            sanban_auction_amount is not None
            and erban_auction_vol is not None
            and erban_auction_vol > 0
        ):
            ratio1 = round(sanban_auction_amount / erban_auction_vol, 4)
            r1_rating, r1_color = _rate_indicator1(ratio1)
            if not basic_pass:
                r1_color = COLOR_GREY

        # ---- 指标2: 竞流比 = 三板竞价金额 / 二板自由流通市值 ----
        jingliu = None
        r2_rating = "不达标"
        r2_color = COLOR_GREY
        if (
            sanban_auction_amount is not None
            and free_float_cap > 0
        ):
            jingliu = round(sanban_auction_amount / free_float_cap * 100, 4)
            r2_rating, r2_color = _rate_indicator2(jingliu, free_float_cap)
            if not basic_pass:
                r2_color = COLOR_GREY

        # ---- 综合评级 ----
        overall, overall_color = _overall_rating(r1_rating, r2_rating, basic_pass)

        results.append({
            "股票代码": code,
            "股票名称": name,
            "行业涨停数": industry_zt_count,
            "三板竞价涨幅": sanban_jia_change if sanban_jia_change is not None else "N/A",
            "三板竞价金额": sanban_auction_amount if sanban_auction_amount is not None else "N/A",
            "二板竞价涨幅": erban_jia_change if erban_jia_change is not None else "N/A",
            "二板竞价金额": erban_auction_vol if erban_auction_vol is not None else "N/A",
            "二板自由流通市值": free_float_cap if free_float_cap > 0 else "N/A",
            "指标1:三板/二板竞价金额": ratio1 if ratio1 is not None else "N/A",
            "指标2:竞流比(%)": jingliu if jingliu is not None else "N/A",
            "二板最后涨停时间": last_zt_time,
            "行业": industry,
            "评级": overall,
            # 内部标记（不输出到Excel）
            "_basic_pass": basic_pass,
            "_overall_color": overall_color,
            "_r1_rating": r1_rating,
            "_r1_color": r1_color,
            "_r2_rating": r2_rating,
            "_r2_color": r2_color,
            "_sanban_jia_change": sanban_jia_change,
            "_erban_jia_change": erban_jia_change,
            "_sanban_auction_amount": sanban_auction_amount,
            "_erban_auction_vol": erban_auction_vol,
            "_free_float_cap": free_float_cap,
        })

        time.sleep(0.15)

    # 5. 排序：达标在前（按指标1降序），不达标在后
    results.sort(key=lambda x: (
        0 if x["_basic_pass"] else 1,
        -(x.get("指标1:三板/二板竞价金额") if isinstance(x.get("指标1:三板/二板竞价金额"), (int, float)) else 0),
    ))

    return results, sanban_date, erban_date, yiban_date


def _fetch_candidate_spot_data(codes: List[str]) -> Dict[str, dict]:
    """
    获取候选股实时行情，优先东方财富，失败回退新浪

    codes: 6位代码列表
    返回: {code: {"name": str, "open": float, "prev_close": float}}
    """
    if not codes:
        return {}

    # 策略1：尝试东方财富全量快照（快速，一次请求覆盖全部候选股）
    try:
        df = get_today_spot_data()
        if df is not None and not df.empty:
            spot_data = {}
            for _, row in df.iterrows():
                c = str(row.get("代码", "")).zfill(6)
                if c in codes:
                    spot_data[c] = {
                        "name": row.get("名称", c),
                        "open": float(row.get("今开", 0) or 0),
                        "prev_close": float(row.get("昨收", 0) or 0),
                    }
            if spot_data:
                return spot_data
    except Exception:
        pass

    # 策略2：新浪财经批量接口（只拉候选股，轻量）
    return get_spot_for_codes_sina(codes)


def _get_auction_amount_for_date(symbol: str, date_str: str) -> Optional[float]:
    """
    获取指定日期的竞价成交额（9:15-9:25 集合竞价时段）
    多策略：CDN trends2 → pre_min_em → minute K线 → Sina 首分钟
    """
    import akshare as ak
    from data_fetcher import get_latest_trading_day, _get_auction_data_via_cdn, _get_auction_data_via_sina
    from auto_picker.data_fetcher import _parse_auction_from_df

    latest_day = get_latest_trading_day()
    is_today = (date_str == latest_day)

    # 策略1：CDN trends2 接口（最可靠，含真正的 9:15-9:25 竞价时段数据）
    result = _get_auction_data_via_cdn(symbol)
    if result is not None:
        return result.get("auction_amount")

    # 策略2：当日 → 盘前分钟接口
    if is_today:
        try:
            df = ak.stock_zh_a_hist_pre_min_em(symbol=symbol)
        except Exception:
            df = None

        if df is not None and len(df) > 0:
            result = _parse_auction_from_df(df)
            if result is not None:
                return result

    # 策略3：历史日期 → 1分钟K线接口
    try:
        df = ak.stock_zh_a_hist_min_em(
            symbol=symbol,
            period="1",
            start_date=f"{date_str} 09:00:00",
            end_date=f"{date_str} 10:00:00",
            adjust="",
        )
    except Exception:
        df = None

    if df is not None and len(df) > 0:
        result = _parse_auction_from_df(df)
        if result is not None:
            return result

    # 策略4：新浪分钟数据首分钟成交额（兜底，适用于历史日期）
    result = _get_auction_data_via_sina(symbol, date_str)
    if result is not None:
        return result.get("auction_amount")

    return None
