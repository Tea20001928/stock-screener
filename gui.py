"""
股票连板筛选程序 - GUI 窗口（基于 tkinter）
用法: python gui.py
"""

import sys
import os
import threading
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from screener import screen_consecutive_limit_up, determine_target_dates
from excel_writer import write_excel, OUTPUT_DIR
from config import COLUMNS


class StockScreenerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("股票连板筛选程序")
        self.root.geometry("1100x680")
        self.root.minsize(900, 600)

        # 设置样式
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # 数据存储
        self.stock_list = []
        self.current_date = ""
        self.prev_date = ""
        self.output_filepath = ""

        # 构建界面
        self._build_header()
        self._build_control_panel()
        self._build_progress_area()
        self._build_result_table()
        self._build_status_bar()

        # 启动时自动检测日期
        self.root.after(100, self._auto_detect_dates)

    def _build_header(self):
        """顶部标题栏"""
        header_frame = tk.Frame(self.root, bg="#2B579A", height=60)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame,
            text="📊 股票连板筛选程序",
            font=("微软雅黑", 18, "bold"),
            fg="white",
            bg="#2B579A",
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=12)

        subtitle_label = tk.Label(
            header_frame,
            text="筛选连续两天涨停的股票（连板股复盘工具）",
            font=("微软雅黑", 10),
            fg="#B0C4DE",
            bg="#2B579A",
        )
        subtitle_label.pack(side=tk.LEFT, padx=10, pady=20)

    def _build_control_panel(self):
        """控制面板"""
        panel = tk.Frame(self.root, bg="#F0F4F8", height=80)
        panel.pack(fill=tk.X, padx=0, pady=0)
        panel.pack_propagate(False)

        # 左侧：日期信息
        date_frame = tk.Frame(panel, bg="#F0F4F8")
        date_frame.pack(side=tk.LEFT, padx=15, pady=12)

        tk.Label(
            date_frame, text="交易日检测:", font=("微软雅黑", 10, "bold"), bg="#F0F4F8"
        ).pack(side=tk.LEFT)

        self.date_label = tk.Label(
            date_frame,
            text="检测中...",
            font=("微软雅黑", 10),
            bg="#F0F4F8",
            fg="#333333",
        )
        self.date_label.pack(side=tk.LEFT, padx=8)

        # 右侧：按钮
        btn_frame = tk.Frame(panel, bg="#F0F4F8")
        btn_frame.pack(side=tk.RIGHT, padx=15, pady=12)

        self.run_btn = tk.Button(
            btn_frame,
            text="▶ 执行筛选",
            font=("微软雅黑", 11, "bold"),
            bg="#2B579A",
            fg="white",
            activebackground="#1E3F6F",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            padx=20,
            pady=6,
            command=self._start_screening,
        )
        self.run_btn.pack(side=tk.RIGHT, padx=5)

        self.open_btn = tk.Button(
            btn_frame,
            text="📁 打开文件位置",
            font=("微软雅黑", 10),
            bg="#5C9BD5",
            fg="white",
            activebackground="#4472C4",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            padx=15,
            pady=6,
            command=self._open_file_location,
            state=tk.DISABLED,
        )
        self.open_btn.pack(side=tk.RIGHT, padx=5)

        self.save_btn = tk.Button(
            btn_frame,
            text="💾 另存为...",
            font=("微软雅黑", 10),
            bg="#5C9BD5",
            fg="white",
            activebackground="#4472C4",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            padx=15,
            pady=6,
            command=self._save_as,
            state=tk.DISABLED,
        )
        self.save_btn.pack(side=tk.RIGHT, padx=5)

    def _build_progress_area(self):
        """进度和日志区域"""
        progress_frame = tk.Frame(self.root, bg="white", height=60)
        progress_frame.pack(fill=tk.X, padx=15, pady=(10, 0))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            length=400,
        )
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(8, 0))

        self.status_text = tk.StringVar(value="就绪 - 点击「执行筛选」开始")
        status_label = tk.Label(
            progress_frame,
            textvariable=self.status_text,
            font=("微软雅黑", 9),
            fg="#666666",
            bg="white",
            anchor="w",
        )
        status_label.pack(fill=tk.X, padx=10, pady=(3, 5))

    def _build_result_table(self):
        """结果表格（Treeview + 滚动条）"""
        table_frame = tk.Frame(self.root, bg="white")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # 简化的列名（GUI 中太宽放不下全部字段）
        self.display_columns = [
            "股票代码", "股票名称", "股票价格", "自由流通盘金额",
            "行业", "最后涨停时间", "二板竞价涨幅", "二板竞价成交量",
            "二板交易量", "一板竞价涨幅", "一板竞价成交量", "一板交易量",
            "竞价/流通盘", "二/一交易量", "二/一竞价量", "二/一竞价涨幅",
        ]

        self.column_map = dict(zip(self.display_columns, COLUMNS))

        # 滚动条
        vsb = ttk.Scrollbar(table_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        hsb = ttk.Scrollbar(table_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        # Treeview
        self.tree = ttk.Treeview(
            table_frame,
            columns=self.display_columns,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            height=16,
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        # 列设置
        col_widths_display = {
            "股票代码": 90,
            "股票名称": 90,
            "股票价格": 70,
            "自由流通盘金额": 120,
            "行业": 90,
            "最后涨停时间": 110,
            "二板竞价涨幅": 100,
            "二板竞价成交量": 120,
            "二板交易量": 120,
            "一板竞价涨幅": 100,
            "一板竞价成交量": 120,
            "一板交易量": 120,
            "竞价/流通盘": 100,
            "二/一交易量": 100,
            "二/一竞价量": 100,
            "二/一竞价涨幅": 100,
        }

        for col in self.display_columns:
            self.tree.heading(col, text=col, anchor="center")
            width = col_widths_display.get(col, 100)
            self.tree.column(col, width=width, anchor="center", minwidth=60)

        self.tree.pack(fill=tk.BOTH, expand=True)

        # 空状态提示
        self._show_empty_hint()

    def _show_empty_hint(self):
        """清空表格并显示提示"""
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _build_status_bar(self):
        """底部状态栏"""
        status_frame = tk.Frame(self.root, bg="#E8EDF2", height=28)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        status_frame.pack_propagate(False)

        self.count_label = tk.Label(
            status_frame,
            text="筛选结果: 0 只连板股",
            font=("微软雅黑", 9),
            bg="#E8EDF2",
            fg="#555555",
        )
        self.count_label.pack(side=tk.LEFT, padx=15, pady=4)

        self.output_label = tk.Label(
            status_frame,
            text="",
            font=("微软雅黑", 9),
            bg="#E8EDF2",
            fg="#888888",
        )
        self.output_label.pack(side=tk.RIGHT, padx=15, pady=4)

    def _auto_detect_dates(self):
        """启动时自动检测交易日"""
        try:
            current_date, prev_date, is_latest = determine_target_dates()
            self.current_date = current_date
            self.prev_date = prev_date

            status = "最近交易日" if is_latest else "指定日期"
            self.date_label.config(
                text=f"二板: {current_date}  |  一板: {prev_date}  ({status})",
                fg="#2B579A",
            )
        except Exception as e:
            self.date_label.config(text=f"日期检测失败: {e}", fg="red")

    def _start_screening(self):
        """在后台线程中执行筛选（避免阻塞 GUI）"""
        self.run_btn.config(state=tk.DISABLED, text="⏳ 筛选中...")
        self.progress_var.set(0)
        self.status_text.set("正在初始化...")
        self._show_empty_hint()

        thread = threading.Thread(target=self._run_screening, daemon=True)
        thread.start()

    def _run_screening(self):
        """实际的筛选逻辑（在后台线程中运行）"""
        try:
            def progress_callback(msg: str, pct: float = None):
                """线程安全的进度更新"""
                self.root.after(0, lambda: self._update_progress(msg, pct))

            stock_list, current_date, prev_date = screen_consecutive_limit_up(
                progress_callback=progress_callback
            )

            # 生成 Excel
            self.root.after(0, lambda: self.status_text.set("正在生成 Excel 报表..."))
            filepath = write_excel(stock_list, current_date, prev_date)

            # 更新 UI（主线程）
            self.root.after(
                0,
                lambda: self._on_screening_done(stock_list, current_date, prev_date, filepath),
            )

        except Exception as e:
            self.root.after(0, lambda: self._on_screening_error(str(e)))

    def _update_progress(self, msg: str, pct: float = None):
        """更新进度条和状态文字"""
        self.status_text.set(msg)
        if pct is not None:
            self.progress_var.set(pct * 100)

    def _on_screening_done(self, stock_list, current_date, prev_date, filepath):
        """筛选完成后的UI更新"""
        self.stock_list = stock_list
        self.current_date = current_date
        self.prev_date = prev_date
        self.output_filepath = filepath

        # 恢复按钮
        self.run_btn.config(state=tk.NORMAL, text="▶ 执行筛选")
        self.open_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.NORMAL)

        # 进度
        self.progress_var.set(100)
        self.status_text.set(f"✅ 筛选完成！{prev_date} → {current_date}，共 {len(stock_list)} 只连板股")

        # 填充表格
        self._populate_table(stock_list)

        # 更新状态栏
        self.count_label.config(text=f"筛选结果: {len(stock_list)} 只连板股")
        self.output_label.config(text=f"文件: {os.path.basename(filepath)}")

    def _on_screening_error(self, error_msg: str):
        """筛选出错后的UI更新"""
        self.run_btn.config(state=tk.NORMAL, text="▶ 执行筛选")
        self.progress_var.set(0)
        self.status_text.set(f"❌ 筛选失败: {error_msg}")
        self.count_label.config(text="筛选结果: 出错")
        messagebox.showerror("筛选失败", f"执行出错:\n\n{error_msg}")

    def _populate_table(self, stock_list):
        """将筛选结果填充到表格中"""
        self._show_empty_hint()

        for i, stock in enumerate(stock_list):
            values = []
            for display_col in self.display_columns:
                actual_col = self.column_map.get(display_col, display_col)
                val = stock.get(actual_col, "N/A")

                # 格式化显示
                if isinstance(val, float):
                    if "涨幅" in display_col and "比值" not in display_col and "/" not in display_col:
                        val = f"{val:.2f}%"
                    elif "竞价/流通盘" in display_col or "/" in display_col:
                        val = f"{val:.4f}"
                    elif any(k in display_col for k in ("金额", "交易量", "成交量", "流通盘")):
                        if val >= 1e8:
                            val = f"{val / 1e8:.2f}亿"
                        elif val >= 1e4:
                            val = f"{val / 1e4:.2f}万"
                        else:
                            val = f"{val:.0f}"
                    else:
                        val = f"{val:.2f}"

                values.append(str(val) if val is not None else "N/A")

            # 交替行颜色
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", tk.END, values=values, tags=(tag,))

        # 配置行颜色
        self.tree.tag_configure("even", background="#F2F7FB")
        self.tree.tag_configure("odd", background="white")

    def _open_file_location(self):
        """在资源管理器中打开输出文件夹"""
        if self.output_filepath and os.path.exists(self.output_filepath):
            subprocess.Popen(["explorer", "/select,", self.output_filepath])
        elif os.path.exists(OUTPUT_DIR):
            subprocess.Popen(["explorer", OUTPUT_DIR])
        else:
            messagebox.showinfo("提示", "输出文件夹尚未创建，请先执行筛选。")

    def _save_as(self):
        """另存为 Excel 文件"""
        if not self.stock_list:
            messagebox.showinfo("提示", "请先执行筛选，再保存文件。")
            return

        filepath = filedialog.asksaveasfilename(
            title="另存为 Excel 文件",
            defaultextension=".xlsx",
            filetypes=[
                ("Excel 文件", "*.xlsx"),
                ("所有文件", "*.*"),
            ],
            initialdir=os.path.expanduser("~\\Desktop"),
            initialfile=f"连板股复盘_{self.current_date.replace('-', '')}.xlsx",
        )

        if filepath:
            try:
                # 直接写入用户选择的路径
                write_excel(self.stock_list, self.current_date, self.prev_date)
                # 如果路径不同，复制文件
                if filepath != self.output_filepath:
                    import shutil
                    shutil.copy2(self.output_filepath, filepath)
                self.status_text.set(f"✅ 已保存到: {filepath}")
                messagebox.showinfo("保存成功", f"文件已保存到:\n{filepath}")
            except Exception as e:
                messagebox.showerror("保存失败", f"保存文件时出错:\n{e}")


def main():
    root = tk.Tk()

    # 设置窗口图标（如果有的话）
    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = StockScreenerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
