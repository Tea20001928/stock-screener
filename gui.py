"""
股票筛选程序 - GUI 窗口（基于 tkinter）
两个独立功能：连板复盘 | 自动选股
用法: python gui.py
"""

import sys
import os
import threading
import subprocess

# PyInstaller 兼容：exe打包后路径不同
if getattr(sys, 'frozen', False):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from screener import screen_consecutive_limit_up, determine_target_dates
from excel_writer import write_excel, OUTPUT_DIR
from config import COLUMNS as COLUMNS_REVIEW

# 自动选股模块（可能因 exe 打包问题导入失败，延迟加载）
_auto_pick_available = True
try:
    from auto_picker.screener import screen_auto_pick
    from auto_picker.excel_writer import write_excel as write_excel_auto
    from auto_picker.config import COLUMNS as COLUMNS_AUTO
except ImportError as e:
    _auto_pick_available = False
    _auto_import_error = str(e)


class BasePanel(ttk.Frame):
    """功能面板基类"""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.stock_list = []
        self.output_filepath = ""
        self._build()

    def _build(self):
        raise NotImplementedError

    def _start_thread(self, target):
        self.app.status_text.set("正在初始化...")
        self.app.progress_var.set(0)
        self.set_buttons_state(tk.DISABLED)
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def _update_progress(self, msg, pct=None):
        self.app.root.after(0, lambda: self._do_update(msg, pct))

    def _do_update(self, msg, pct):
        self.app.status_text.set(msg)
        if pct is not None:
            self.app.progress_var.set(pct * 100)

    def set_buttons_state(self, state):
        for btn in getattr(self, 'action_buttons', []):
            btn.config(state=state)

    def _open_file_location(self):
        if self.output_filepath and os.path.exists(self.output_filepath):
            subprocess.Popen(["explorer", "/select,", self.output_filepath])
        elif os.path.exists(OUTPUT_DIR):
            subprocess.Popen(["explorer", OUTPUT_DIR])
        else:
            messagebox.showinfo("提示", "输出文件夹尚未创建，请先执行。")


# ============================================================
# 面板1：连板复盘
# ============================================================
class ReviewPanel(BasePanel):
    def _build(self):
        # 控制栏
        ctrl = tk.Frame(self, bg="#F0F4F8", height=50)
        ctrl.pack(fill=tk.X, padx=10, pady=5)
        ctrl.pack_propagate(False)

        self.date_label = tk.Label(ctrl, text="检测中...", font=("微软雅黑", 10),
                                   bg="#F0F4F8", fg="#2B579A")
        self.date_label.pack(side=tk.LEFT, padx=10)

        btns = [
            tk.Button(ctrl, text="执行筛选", font=("微软雅黑", 10, "bold"),
                      bg="#2B579A", fg="white", relief=tk.FLAT, cursor="hand2",
                      padx=15, pady=3, command=self._run),
            tk.Button(ctrl, text="打开文件", font=("微软雅黑", 9),
                      bg="#5C9BD5", fg="white", relief=tk.FLAT, cursor="hand2",
                      padx=10, pady=3, command=self._open_file_location,
                      state=tk.DISABLED),
        ]
        self.action_buttons = btns
        for btn in btns:
            btn.pack(side=tk.RIGHT, padx=3)

        # 结果表格
        tbl_frame = tk.Frame(self, bg="white")
        tbl_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.display_cols = [
            "股票代码", "股票名称", "股票价格", "自由流通盘金额",
            "行业", "最后涨停时间", "二板竞价涨幅", "二板竞价成交量",
            "二板交易量", "一板竞价涨幅", "一板竞价成交量", "一板交易量",
            "竞价/流通盘", "二/一交易量", "二/一竞价量", "二/一竞价涨幅",
        ]
        self.col_map = dict(zip(self.display_cols, COLUMNS_REVIEW))

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree = ttk.Treeview(tbl_frame, columns=self.display_cols,
                                 show="headings", yscrollcommand=vsb.set,
                                 xscrollcommand=hsb.set, height=14)
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        widths = [90, 90, 70, 110, 80, 100, 90, 110, 110, 90, 110, 110, 90, 90, 90, 90]
        for i, col in enumerate(self.display_cols):
            self.tree.heading(col, text=col, anchor="center")
            self.tree.column(col, width=widths[i], anchor="center", minwidth=60)

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.tag_configure("even", background="#F2F7FB")
        self.tree.tag_configure("odd", background="white")

        # 启动日期检测
        self.after(100, self._detect_dates)

    def _detect_dates(self):
        try:
            current_date, prev_date, is_latest = determine_target_dates()
            status = "最近交易日" if is_latest else "指定"
            self.date_label.config(
                text=f"二板: {current_date}  |  一板: {prev_date}  ({status})",
                fg="#2B579A")
        except Exception as e:
            self.date_label.config(text=f"日期检测失败: {e}", fg="red")

    def _run(self):
        self._start_thread(self._do_run)

    def _do_run(self):
        try:
            def cb(msg, pct=None):
                self._update_progress(msg, pct)

            stock_list, cur_d, prev_d = screen_consecutive_limit_up(progress_callback=cb)

            self._update_progress("正在生成 Excel 报表...", None)
            filepath = write_excel(stock_list, cur_d, prev_d)

            def done():
                self.stock_list = stock_list
                self.output_filepath = filepath
                self.set_buttons_state(tk.NORMAL)
                self._update_progress(
                    f"[OK] {prev_d} -> {cur_d}，共 {len(stock_list)} 只连板股", 1.0)
                self._fill_table(stock_list)
                self.app.count_label.config(text=f"连板复盘: {len(stock_list)} 只连板股")
            self.app.root.after(0, done)

        except Exception as e:
            def err():
                self.set_buttons_state(tk.NORMAL)
                self._update_progress(f"[ERROR] {e}", 0)
                messagebox.showerror("筛选失败", str(e))
            self.app.root.after(0, err)

    def _fill_table(self, stock_list):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, stock in enumerate(stock_list):
            vals = []
            for dc in self.display_cols:
                ac = self.col_map.get(dc, dc)
                v = stock.get(ac, "N/A")
                if isinstance(v, float):
                    if "涨幅" in dc and "比值" not in dc and "/" not in dc:
                        v = f"{v:.2f}%"
                    elif "/" in dc:
                        v = f"{v:.4f}"
                    elif any(k in dc for k in ("金额", "交易量", "成交量", "流通盘")):
                        v = f"{v/1e8:.2f}亿" if v >= 1e8 else f"{v/1e4:.2f}万" if v >= 1e4 else f"{v:.0f}"
                    else:
                        v = f"{v:.2f}"
                vals.append(str(v) if v is not None else "N/A")
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", tk.END, values=vals, tags=(tag,))


# ============================================================
# 面板2：自动选股
# ============================================================
class AutoPickPanel(BasePanel):
    def _build(self):
        ctrl = tk.Frame(self, bg="#FFF8E1", height=50)
        ctrl.pack(fill=tk.X, padx=10, pady=5)
        ctrl.pack_propagate(False)

        info = tk.Label(ctrl, text="三板=当天(竞价后) | 筛选一板+二板连板股，三板竞价评分",
                        font=("微软雅黑", 9), bg="#FFF8E1", fg="#795548")
        info.pack(side=tk.LEFT, padx=10)

        btns = [
            tk.Button(ctrl, text="执行选股", font=("微软雅黑", 10, "bold"),
                      bg="#E65100", fg="white", relief=tk.FLAT, cursor="hand2",
                      padx=15, pady=3, command=self._run),
            tk.Button(ctrl, text="打开文件", font=("微软雅黑", 9),
                      bg="#8D6E63", fg="white", relief=tk.FLAT, cursor="hand2",
                      padx=10, pady=3, command=self._open_file_location,
                      state=tk.DISABLED),
        ]
        self.action_buttons = btns
        for btn in btns:
            btn.pack(side=tk.RIGHT, padx=3)

        # 图例
        legend = tk.Frame(ctrl, bg="#FFF8E1")
        legend.pack(side=tk.RIGHT, padx=15)
        for text, color in [("优选", "#92D050"), ("合格", "#FFC000"),
                             ("不合格", "#FF6B6B"), ("不达标", "#C0C0C0")]:
            tk.Label(legend, text=f" {text} ", bg=color, font=("微软雅黑", 8),
                     fg="white", width=6).pack(side=tk.RIGHT, padx=1)

        # 结果表格
        tbl_frame = tk.Frame(self, bg="white")
        tbl_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.display_cols = [
            "股票代码", "股票名称", "三板竞价涨幅", "三板竞价金额",
            "二板竞价涨幅", "二板竞价金额", "二板自由流通市值",
            "指标1:三板/二板竞价金额", "指标2:竞流比(%)",
            "二板最后涨停时间", "行业", "评级",
        ]

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree = ttk.Treeview(tbl_frame, columns=self.display_cols,
                                 show="headings", yscrollcommand=vsb.set,
                                 xscrollcommand=hsb.set, height=14)
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        widths = [90, 90, 90, 110, 90, 110, 110, 130, 100, 110, 80, 70]
        for i, col in enumerate(self.display_cols):
            self.tree.heading(col, text=col, anchor="center")
            self.tree.column(col, width=widths[i], anchor="center", minwidth=60)

        self.tree.pack(fill=tk.BOTH, expand=True)

        # 颜色标签
        self.tree.tag_configure("green", background="#E2F5D5")
        self.tree.tag_configure("yellow", background="#FFF3CD")
        self.tree.tag_configure("red", background="#FFD6D6")
        self.tree.tag_configure("grey", background="#E8E8E8")

    def _run(self):
        # 检查模块是否可用
        if not _auto_pick_available:
            messagebox.showerror(
                "模块加载失败",
                f"自动选股模块未能加载，可能是打包问题。\n\n"
                f"错误详情: {_auto_import_error}\n\n"
                f"请尝试用源码运行: python gui.py"
            )
            return

        # 预先检查交易日，非交易日直接弹窗阻止
        from datetime import datetime
        from data_fetcher import get_recent_trading_days
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            recent = get_recent_trading_days(3)
        except Exception as e:
            import traceback
            detail = traceback.format_exc()
            # 写桌面日志
            log_path = os.path.join(os.path.expanduser("~"), "Desktop", "程序错误日志.txt")
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(f"交易日检测异常 - {datetime.now()}\n{detail}")
            except Exception:
                pass
            messagebox.showerror(
                "交易日检测失败",
                f"无法获取交易日历，请检查网络连接。\n\n"
                f"错误: {str(e)[:300]}\n\n"
                f"完整日志已写入桌面: 程序错误日志.txt"
            )
            return

        try:
            if today_str != recent[0]:
                messagebox.showwarning(
                    "无法运行 - 非交易日",
                    f"今天是 {today_str}，不是交易日！\n\n"
                    f"最近交易日为 {recent[0]}。\n"
                    f"自动选股功能只能在交易日 9:25 竞价结束后运行。\n\n"
                    f"请切换到「连板复盘」选项卡进行复盘。"
                )
                return
        except Exception as e:
            messagebox.showerror("错误", f"交易日判定失败: {e}")

        self._start_thread(self._do_run)

    def _do_run(self):
        try:
            def cb(msg, pct=None):
                self._update_progress(msg, pct)

            results, sanban, erban, yiban = screen_auto_pick(progress_callback=cb)

            self._update_progress("正在生成 Excel 报表...", None)
            filepath = write_excel_auto(results, sanban, erban, yiban)

            def done():
                self.stock_list = results
                self.output_filepath = filepath
                self.set_buttons_state(tk.NORMAL)

                good = sum(1 for r in results if r.get("_basic_pass"))
                preferred = sum(1 for r in results if r.get("评级") == "优选")
                self._update_progress(
                    f"[OK] 三板{sanban} | 共{len(results)}只 | 达标{good}只 | 优选{preferred}只",
                    1.0)
                self._fill_table(results)
                self.app.count_label.config(
                    text=f"自动选股: {len(results)} 只候选, {good} 只达标")
            self.app.root.after(0, done)

        except Exception as e:
            def err():
                self.set_buttons_state(tk.NORMAL)
                self._update_progress(f"[ERROR] {e}", 0)
                messagebox.showerror("选股失败", str(e))
            self.app.root.after(0, err)

    def _fill_table(self, results):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for stock in results:
            vals = []
            for dc in self.display_cols:
                v = stock.get(dc, "N/A")
                if isinstance(v, float):
                    if "涨幅" in dc:
                        v = f"{v:.2f}%"
                    elif "竞流比" in dc:
                        v = f"{v:.4f}%"
                    elif "指标1" in dc:
                        v = f"{v:.4f}"
                    elif "金额" in dc or "市值" in dc:
                        v = f"{v/1e8:.2f}亿" if v >= 1e8 else f"{v/1e4:.2f}万"
                vals.append(str(v) if v is not None else "N/A")

            color = stock.get("_overall_color", "#C0C0C0")
            tag_map = {
                "#92D050": "green",
                "#FFC000": "yellow",
                "#FF6B6B": "red",
                "#C0C0C0": "grey",
            }
            tag = tag_map.get(color, "grey")
            self.tree.insert("", tk.END, values=vals, tags=(tag,))


# ============================================================
# 主窗口
# ============================================================
class StockScreenerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("股票筛选程序")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)

        self._build_header()
        self._build_progress()
        self._build_tabs()
        self._build_status()

    def _build_header(self):
        frame = tk.Frame(self.root, bg="#2B579A", height=55)
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)
        tk.Label(frame, text="股票筛选程序",
                 font=("微软雅黑", 16, "bold"), fg="white", bg="#2B579A"
                 ).pack(side=tk.LEFT, padx=20, pady=12)

    def _build_progress(self):
        frame = tk.Frame(self.root, bg="white", height=45)
        frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(frame, variable=self.progress_var,
                                            maximum=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X, padx=5, pady=(5, 0))
        self.status_text = tk.StringVar(value="就绪")
        tk.Label(frame, textvariable=self.status_text, font=("微软雅黑", 9),
                 fg="#666", bg="white", anchor="w").pack(fill=tk.X, padx=5)

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.review_panel = ReviewPanel(self.notebook, self)
        self.auto_panel = AutoPickPanel(self.notebook, self)

        self.notebook.add(self.review_panel, text="  连板复盘  ")
        self.notebook.add(self.auto_panel, text="  自动选股  ")

    def _build_status(self):
        frame = tk.Frame(self.root, bg="#E8EDF2", height=25)
        frame.pack(fill=tk.X, side=tk.BOTTOM)
        frame.pack_propagate(False)
        self.count_label = tk.Label(frame, text="就绪",
                                    font=("微软雅黑", 9), bg="#E8EDF2", fg="#555")
        self.count_label.pack(side=tk.LEFT, padx=15, pady=3)


def main():
    root = tk.Tk()
    app = StockScreenerApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 写入错误日志到桌面
        import traceback
        log_path = os.path.join(os.path.expanduser("~"), "Desktop", "程序错误日志.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"错误时间: {__import__('datetime').datetime.now()}\n")
            f.write(f"错误类型: {type(e).__name__}\n")
            f.write(f"错误信息: {e}\n\n")
            f.write(traceback.format_exc())
        # 也尝试弹窗
        try:
            messagebox.showerror("程序启动失败", f"错误已写入桌面: 程序错误日志.txt\n\n{str(e)[:200]}")
        except Exception:
            pass
        raise
