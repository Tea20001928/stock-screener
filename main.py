"""
股票连板筛选程序 - CLI 入口
用法: python main.py
"""

import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screener import screen_consecutive_limit_up
from excel_writer import write_excel


def progress_handler(msg: str, pct: float = None):
    """CLI 进度输出"""
    if pct is not None:
        pct_str = f" [{pct * 100:.0f}%]"
    else:
        pct_str = ""
    print(f"  {msg}{pct_str}")


def main():
    print("=" * 60)
    print("  股票连板筛选程序 - Stock Screener")
    print("  筛选连续两天涨停的股票（连板股）")
    print("=" * 60)
    print()

    try:
        # 执行筛选
        print("开始筛选...")
        stock_list, current_date, prev_date = screen_consecutive_limit_up(
            progress_callback=progress_handler
        )

        # 生成 Excel
        print()
        print("生成 Excel 报表...")
        filepath = write_excel(stock_list, current_date, prev_date)

        print()
        print("=" * 60)
        print(f"  [OK] 筛选完成！共找到 {len(stock_list)} 只连板股")
        print(f"  二板（当前）: {current_date}")
        print(f"  一板（前日）: {prev_date}")
        print(f"  报表文件: {filepath}")
        print("=" * 60)

    except ValueError as e:
        print()
        print(f"  [WARN] {e}")
        print("  请确认：1) 数据源可访问  2) 日期正确  3) 盘后数据已更新")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"  [ERROR] 运行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
