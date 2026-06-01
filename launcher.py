"""
股票筛选程序 — 统一启动器
双击运行，选择要使用的功能
"""

import sys
import os


def main():
    print("=" * 50)
    print("  股票筛选工具 v2.0")
    print("=" * 50)
    print()
    print("  [1] 连板复盘 — 筛选连续两天涨停的连板股")
    print("      运行时机：交易日 15:30 盘后")
    print()
    print("  [2] 自动选股 — 三板竞价数据评分选股")
    print("      运行时机：交易日 9:25 竞价结束后")
    print()
    print("  [0] 退出")
    print()

    while True:
        try:
            choice = input("请选择功能 [1/2/0]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出")
            sys.exit(0)

        if choice == "1":
            print()
            from main import main as run_main
            run_main()
            break
        elif choice == "2":
            print()
            from auto_picker.main import main as run_auto
            run_auto()
            break
        elif choice == "0":
            print("已退出")
            sys.exit(0)
        else:
            print("输入错误，请输入 1、2 或 0")


if __name__ == "__main__":
    main()
