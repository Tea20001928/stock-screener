"""
数据抓取模块 - 获取涨停股、日线、竞价等数据
数据源：东方财富（通过 akshare 和直接 HTTP 接口）
"""

import time
import pandas as pd
import akshare as ak
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

from config import (
    ZT_KEEP_FIELDS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
)


def _retry(func, *args, **kwargs):
    """带重试的函数执行"""
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
    raise last_err


def _code_to_market(code: str) -> Tuple[str, str]:
    """
    将6位股票代码转换为市场标识
    返回: (市场前缀, 东方财富市场代码)
        sh/1 = 上海, sz/0 = 深圳, bj/0 = 北京
    """
    code = str(code).zfill(6)
    if code.startswith("6"):
        return "sh", "1"
    elif code.startswith(("0", "3")):
        return "sz", "0"
    elif code.startswith(("8", "4")):
        return "bj", "0"
    else:
        return "sz", "0"


def _code_to_eastmoney_secid(code: str) -> str:
    """转换为东方财富 secid 格式（如 1.600000 或 0.000001）"""
    _, market = _code_to_market(code)
    return f"{market}.{code}"


def _format_limit_up_time(time_val) -> str:
    """
    格式化涨停封板时间
    输入可能是 int(92500) 或 str("092500")
    输出格式: "09:25:00"
    """
    if pd.isna(time_val) or time_val == "" or time_val is None:
        return "N/A"
    try:
        time_str = str(int(time_val)).zfill(6)
        return f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
    except (ValueError, TypeError):
        return str(time_val)


def get_recent_trading_days(n: int = 5) -> list:
    """
    获取最近 n 个交易日（日期从近到远排列）
    返回格式: ["2025-05-30", "2025-05-29", ...]
    """
    trade_dates_df = _retry(ak.tool_trade_date_hist_sina)
    dates = trade_dates_df["trade_date"].tolist()
    # 过滤掉未来日期
    today_str = datetime.now().strftime("%Y-%m-%d")
    dates = [d for d in dates if str(d) <= today_str]
    # 取最近 n 个，从近到远
    recent = sorted(dates, reverse=True)[:n]
    return [str(d) for d in recent]


def get_latest_trading_day() -> str:
    """获取最近一个交易日（不含未来），格式: 'YYYY-MM-DD'"""
    days = get_recent_trading_days(1)
    if not days:
        raise RuntimeError("无法获取交易日数据")
    return days[0]


def get_limit_up_stocks(date_str: str) -> pd.DataFrame:
    """
    获取指定日期的涨停股列表
    date_str: 'YYYY-MM-DD' 或 'YYYYMMDD'
    返回 DataFrame，包含代码、名称、最新价、流通市值、行业、封板时间、成交额等
    """
    date_compact = date_str.replace("-", "")

    # 判断是否为最近交易日（用于选择API）
    latest_day = get_latest_trading_day()
    latest_compact = latest_day.replace("-", "")

    try:
        if date_compact == latest_compact:
            df = _retry(ak.stock_zt_pool_em, date=date_compact)
        else:
            df = _retry(ak.stock_zt_pool_em, date=date_compact)
    except Exception:
        try:
            df = _retry(ak.stock_zt_pool_previous_em)
        except Exception as e:
            raise RuntimeError(f"获取 {date_str} 涨停数据失败: {e}")

    if df is None or len(df) == 0:
        return pd.DataFrame(columns=ZT_KEEP_FIELDS)

    available_fields = [f for f in ZT_KEEP_FIELDS if f in df.columns]
    result = df[available_fields].copy()

    if "代码" in result.columns:
        result["代码"] = result["代码"].astype(str).str.zfill(6)

    return result


def get_daily_bar(symbol: str, date_str: str, prev_date_str: str = None) -> Optional[dict]:
    """
    获取个股日线数据（开盘价、昨收、成交额）
    优先使用腾讯数据源（可靠），东方财富作为备选

    symbol: 6位代码如 '000001'
    date_str: 目标日期 'YYYY-MM-DD'
    prev_date_str: 前一个交易日 'YYYY-MM-DD'，用于获取昨收价

    返回: {"open": float, "prev_close": float, "amount": float} 或 None
        amount 单位为元（人民币）
    """
    if prev_date_str:
        start_date = prev_date_str
    else:
        start_date = date_str

    # 转为腾讯格式 symbol（如 sz000001, sh600000）
    prefix, _ = _code_to_market(symbol)
    tx_symbol = f"{prefix}{symbol}"

    df = None
    source = None

    # 策略1：腾讯数据源（周末也可用，更可靠）
    try:
        df = _retry(
            ak.stock_zh_a_hist_tx,
            symbol=tx_symbol,
            start_date=start_date,
            end_date=date_str,
        )
        source = "tx"
    except Exception:
        pass

    # 策略2：东方财富数据源
    if df is None:
        date_compact = date_str.replace("-", "")
        start_compact = start_date.replace("-", "")
        try:
            df = _retry(
                ak.stock_zh_a_hist,
                symbol=symbol,
                period="daily",
                start_date=start_compact,
                end_date=date_compact,
                adjust="",
            )
            source = "em"
        except Exception:
            return None

    if df is None or len(df) == 0:
        return None

    # 根据数据源处理列名
    if source == "tx":
        # 腾讯源：列名为英文 date, open, close, high, low, amount
        # date 列是 datetime.date 对象，需要转为字符串
        # amount 单位是"万"（万元），需转为元
        df["_date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        date_col = "_date_str"
        open_col, close_col, amount_col = "open", "close", "amount"
    else:
        # 东方财富源：列名为中文 日期, 开盘, 收盘, 成交额
        df["_date_str"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        date_col = "_date_str"
        open_col, close_col, amount_col = "开盘", "收盘", "成交额"

    # 找目标日期的行
    target_rows = df[df[date_col] == date_str]
    if len(target_rows) == 0:
        return None

    row = target_rows.iloc[0]
    open_price = float(row.get(open_col, 0) or 0)
    amount_raw = float(row.get(amount_col, 0) or 0)

    # 腾讯数据源的 amount 单位是"万元"，转为"元"
    if source == "tx":
        amount = amount_raw * 10000
    else:
        amount = amount_raw

    # 昨收价 = 前一个交易日的收盘价
    prev_close = 0.0
    prev_rows = df[df[date_col] < date_str]
    if len(prev_rows) > 0:
        prev_close = float(prev_rows.iloc[-1].get(close_col, 0) or 0)

    return {
        "open": open_price,
        "prev_close": prev_close,
        "amount": amount,
    }


def get_auction_data_via_min_kline(symbol: str, date_str: str) -> Optional[dict]:
    """
    通过 akshare 的分钟K线接口获取集合竞价数据（9:15-9:25时段）
    symbol: 6位代码如 '000001'
    date_str: 'YYYY-MM-DD'
    返回: {"auction_amount": float} 或 None
    """
    try:
        df = _retry(
            ak.stock_zh_a_hist_min_em,
            symbol=symbol,
            period="1",
            start_date=f"{date_str} 09:15:00",
            end_date=f"{date_str} 15:00:00",
            adjust="",
        )
    except Exception:
        return None

    if df is None or len(df) == 0:
        return None

    # 检查时间列
    time_col = "时间" if "时间" in df.columns else df.columns[0]
    df[time_col] = df[time_col].astype(str)

    # 过滤 09:15 - 09:25
    auction_rows = df[
        df[time_col].str.contains(r"09:1[5-9]|09:2[0-5]", na=False)
    ]

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

    total_amount = float(auction_rows[amount_col].sum())
    if total_amount > 0:
        return {"auction_amount": total_amount}

    return None


def get_auction_data_pre_min(symbol: str) -> Optional[dict]:
    """
    通过 akshare 盘前分钟接口获取集合竞价数据（仅限最近交易日）
    symbol: 6位代码如 '000001'
    """
    try:
        df = _retry(ak.stock_zh_a_hist_pre_min_em, symbol=symbol)
    except Exception:
        return None

    if df is None or len(df) == 0:
        return None

    time_col = None
    for col in df.columns:
        if "时间" in col or "time" in col.lower():
            time_col = col
            break

    if time_col is None:
        return None

    df[time_col] = df[time_col].astype(str)
    auction_rows = df[
        df[time_col].str.contains(r"09:1[5-9]|09:2[0-5]", na=False)
    ]

    if len(auction_rows) == 0:
        return None

    amount_col = None
    for col in ["成交额", "成交金额"]:
        if col in auction_rows.columns:
            amount_col = col
            break

    if amount_col is None:
        return None

    total_amount = float(auction_rows[amount_col].sum())
    if total_amount > 0:
        return {"auction_amount": total_amount}

    return None


def get_auction_data(symbol: str, date_str: str, is_latest: bool = False) -> Optional[dict]:
    """
    获取集合竞价数据（统一入口，多策略尝试）
    symbol: 6位代码
    date_str: 'YYYY-MM-DD'
    is_latest: 是否为最近交易日
    """
    # 策略1：盘前分钟接口（仅限最近交易日）
    if is_latest:
        result = get_auction_data_pre_min(symbol)
        if result is not None:
            return result

    # 策略2：1分钟K线接口
    result = get_auction_data_via_min_kline(symbol, date_str)
    if result is not None:
        return result

    # 策略3：东方财富 HTTP 接口
    result = _get_auction_data_eastmoney_http(symbol, date_str)
    if result is not None:
        return result

    return None


def _get_auction_data_eastmoney_http(symbol: str, date_str: str) -> Optional[dict]:
    """东方财富 HTTP 接口获取集合竞价数据"""
    date_compact = date_str.replace("-", "")
    secid = _code_to_eastmoney_secid(symbol)

    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&klt=1&fqt=0"
        f"&beg={date_compact}&end={date_compact}"
        f"&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57"
        f"&lmt=500"
    )

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        data = resp.json()

        if data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            auction_amount = 0.0
            for line in klines:
                parts = line.split(",")
                time_part = parts[0].split(" ")[-1] if " " in parts[0] else parts[0]
                if "09:15" <= time_part <= "09:25":
                    if len(parts) >= 7:
                        try:
                            auction_amount += float(parts[6]) if parts[6] != "-" else 0.0
                        except ValueError:
                            pass

            if auction_amount > 0:
                return {"auction_amount": auction_amount}
    except Exception:
        pass

    return None


def enrich_single_stock(
    code: str,
    name: str,
    current_date: str,
    prev_date: str,
    prev_prev_date: str,
    is_latest: bool,
    zt_row: dict,
    prev_zt_row: Optional[dict] = None,
) -> dict:
    """
    为单只股票补齐所有字段

    code: 股票代码
    name: 股票名称
    current_date: 二板日期 (YYYY-MM-DD)
    prev_date: 一板日期 (YYYY-MM-DD)
    prev_prev_date: 一板的前一交易日 (YYYY-MM-DD)，用于计算一板昨收
    is_latest: 是否为最近交易日
    zt_row: 二板涨停数据行
    prev_zt_row: 一板涨停数据行
    """
    result = {
        "股票代码": code,
        "股票名称": name,
        "股票价格": zt_row.get("最新价", "N/A"),
        "自由流通盘金额": zt_row.get("流通市值", "N/A"),
        "行业": zt_row.get("所属行业", "N/A"),
        "当天最后涨停时间": _format_limit_up_time(zt_row.get("最后封板时间")),
    }

    # 设置默认值
    result.update({
        "二板竞价涨幅": "N/A",
        "二板竞价成交量": "N/A",
        "二板交易量": zt_row.get("成交额", "N/A"),
        "一板竞价涨幅": "N/A",
        "一板竞价成交量": "N/A",
        "一板交易量": prev_zt_row.get("成交额", "N/A") if prev_zt_row is not None else "N/A",
        "二板竞价成交量/自由流通盘金额": "N/A",
        "二板/一板交易量": "N/A",
        "二板/一板竞价成交量": "N/A",
        "二板/一板竞价涨幅": "N/A",
    })

    # ---- 二板日线数据 ----
    # 二板的昨收 = 一板的收盘价，所以取 prev_date 作为 start_date
    bar2 = get_daily_bar(code, current_date, prev_date_str=prev_date)
    if bar2 and bar2.get("prev_close", 0) > 0 and bar2.get("open", 0) > 0:
        jia2_change = (bar2["open"] - bar2["prev_close"]) / bar2["prev_close"] * 100
        result["二板竞价涨幅"] = round(jia2_change, 2)

    # 二板竞价成交量
    auction2 = get_auction_data(code, current_date, is_latest=is_latest)
    if auction2 and auction2.get("auction_amount", 0) > 0:
        result["二板竞价成交量"] = auction2["auction_amount"]

    # ---- 一板日线数据 ----
    # 一板的昨收 = 一板前一日的收盘价
    bar1 = get_daily_bar(code, prev_date, prev_date_str=prev_prev_date)
    if bar1 and bar1.get("prev_close", 0) > 0 and bar1.get("open", 0) > 0:
        jia1_change = (bar1["open"] - bar1["prev_close"]) / bar1["prev_close"] * 100
        result["一板竞价涨幅"] = round(jia1_change, 2)

    # 一板竞价成交量
    auction1 = get_auction_data(code, prev_date, is_latest=False)
    if auction1 and auction1.get("auction_amount", 0) > 0:
        result["一板竞价成交量"] = auction1["auction_amount"]

    # ---- 计算比值字段 ----
    free_float = result["自由流通盘金额"]
    er_auction_vol = result["二板竞价成交量"]
    er_vol = result["二板交易量"]
    yi_auction_vol = result["一板竞价成交量"]
    yi_vol = result["一板交易量"]
    er_change = result["二板竞价涨幅"]
    yi_change = result["一板竞价涨幅"]

    # 二板竞价成交量 / 自由流通盘金额
    if (
        isinstance(er_auction_vol, (int, float))
        and isinstance(free_float, (int, float))
        and free_float > 0
    ):
        result["二板竞价成交量/自由流通盘金额"] = round(er_auction_vol / free_float, 6)

    # 二板/一板交易量
    if (
        isinstance(er_vol, (int, float))
        and isinstance(yi_vol, (int, float))
        and yi_vol > 0
    ):
        result["二板/一板交易量"] = round(er_vol / yi_vol, 4)

    # 二板/一板竞价成交量
    if (
        isinstance(er_auction_vol, (int, float))
        and isinstance(yi_auction_vol, (int, float))
        and yi_auction_vol > 0
    ):
        result["二板/一板竞价成交量"] = round(er_auction_vol / yi_auction_vol, 4)

    # 二板/一板竞价涨幅
    if (
        isinstance(er_change, (int, float))
        and isinstance(yi_change, (int, float))
        and yi_change != 0
    ):
        result["二板/一板竞价涨幅"] = round(er_change / yi_change, 4)

    return result


def fetch_all_data(
    current_date: str,
    prev_date: str,
    is_latest: bool,
    progress_callback=None,
) -> Tuple[List[dict], pd.DataFrame, pd.DataFrame]:
    """
    获取两日涨停股并筛选连板股，返回完整数据的列表
    current_date: 二板日期 (YYYY-MM-DD)
    prev_date: 一板日期 (YYYY-MM-DD)
    is_latest: 是否为最近交易日
    progress_callback: 可选进度回调 (msg: str, pct: float)

    返回: (enriched_stocks_list, current_df, prev_df)
    """
    if progress_callback:
        progress_callback("获取交易日历...", 0.05)

    # 获取一板的前一交易日（用于计算一板昨收价）
    recent_days = get_recent_trading_days(10)
    try:
        prev_idx = recent_days.index(prev_date)
        prev_prev_date = recent_days[prev_idx + 1] if prev_idx + 1 < len(recent_days) else prev_date
    except (ValueError, IndexError):
        prev_prev_date = prev_date

    # 1. 获取两日涨停股列表
    if progress_callback:
        progress_callback(f"获取 {current_date} 涨停股列表...", 0.1)

    current_zt = get_limit_up_stocks(current_date)
    if current_zt.empty:
        raise ValueError(f"{current_date} 没有涨停股数据（可能非交易日或数据暂未更新）")

    if progress_callback:
        progress_callback(f"获取 {prev_date} 涨停股列表...", 0.25)

    prev_zt = get_limit_up_stocks(prev_date)
    if prev_zt.empty:
        raise ValueError(f"{prev_date} 没有涨停股数据")

    # 2. 取交集 — 连续涨停的股票
    if progress_callback:
        progress_callback("筛选连板股...", 0.35)

    current_codes = set(current_zt["代码"].tolist())
    prev_codes = set(prev_zt["代码"].tolist())
    consecutive_codes = current_codes & prev_codes

    if not consecutive_codes:
        raise ValueError(f"未找到 {prev_date} 和 {current_date} 连续涨停的股票")

    # 3. 为每只连板股补全数据
    consecutive_list = sorted(consecutive_codes)
    total = len(consecutive_list)
    enriched = []

    # 构建索引
    prev_zt_index = {}
    for _, row in prev_zt.iterrows():
        prev_zt_index[str(row["代码"]).zfill(6)] = row

    current_zt_index = {}
    for _, row in current_zt.iterrows():
        current_zt_index[str(row["代码"]).zfill(6)] = row

    for i, code in enumerate(consecutive_list):
        if progress_callback:
            progress_callback(
                f"获取股票数据 ({i+1}/{total}): {code}",
                0.4 + (0.5 * (i + 1) / total),
            )

        zt_row = current_zt_index.get(code)
        prev_zt_row = prev_zt_index.get(code)
        name = zt_row["名称"] if zt_row is not None else code

        try:
            stock_data = enrich_single_stock(
                code=code,
                name=name,
                current_date=current_date,
                prev_date=prev_date,
                prev_prev_date=prev_prev_date,
                is_latest=is_latest,
                zt_row=zt_row if zt_row is not None else {},
                prev_zt_row=prev_zt_row if prev_zt_row is not None else None,
            )
            enriched.append(stock_data)
        except Exception as e:
            if progress_callback:
                progress_callback(f"警告: {code} {name} 数据获取失败 ({e})", None)
            continue

        time.sleep(0.2)

    return enriched, current_zt, prev_zt
