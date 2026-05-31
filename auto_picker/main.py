"""
自动选股 - CLI 入口
用法: python -m auto_picker.main
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_picker.screener import screen_auto_pick
from auto_picker.excel_writer import write_excel


def progress_handler(msg: str, pct: float = None):
    if pct is not None:
        pct_str = f" [{pct * 100:.0f}%]"
    else:
        pct_str = ""
    print(f"  {msg}{pct_str}")


def main():
    print("=" * 60)
    print("  自动选股程序 - Auto Stock Picker")
    print("  筛选一板+二板连板股，用三板竞价数据评分")
    print("  运行时间：交易日 9:25 竞价结束后")
    print("=" * 60)
    print()

    try:
        print("开始分析...")
        results, sanban_date, erban_date, yiban_date = screen_auto_pick(
            progress_callback=progress_handler
        )

        # 统计
        good = sum(1 for r in results if r.get("_basic_pass"))
        preferred = sum(1 for r in results if r.get("评级") == "优选")
        qualified = sum(1 for r in results if r.get("评级") == "合格")
        failed = sum(1 for r in results if r.get("评级") == "不合格")
        bad = sum(1 for r in results if r.get("评级") == "不达标")

        print()
        print("生成 Excel 报表...")
        filepath = write_excel(results, sanban_date, erban_date, yiban_date)

        print()
        print("=" * 60)
        print(f"  [OK] 分析完成！共 {len(results)} 只候选股")
        print(f"  达基础门槛: {good} 只")
        print(f"    优选(绿): {preferred} | 合格(黄): {qualified} | 不合格(红): {failed}")
        print(f"  不达标(灰): {bad} 只")
        print(f"  报表文件: {filepath}")
        print("=" * 60)

    except ValueError as e:
        print()
        print(f"  [WARN] {e}")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
