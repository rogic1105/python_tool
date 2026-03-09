import argparse
import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from core.base_tool import BaseTool

BRUTE_FORCE_LIMIT = 22


class InvoiceHelperTool(BaseTool):
    name = "invoice_helper"
    display_name = "發票湊數小幫手"
    category = "data"
    description = "從一堆金額中找出總和最接近目標金額的組合（子集合加總問題）"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--file", default="price.txt", help="包含目標與金額的文字檔 (預設: price.txt)")

    def run_cli(self, args) -> None:
        import time
        from tools.data.invoice_helper.invoice_lib import read_price_data, solve_dp, solve_brute_force

        target, numbers = read_price_data(args.file)
        if target is None:
            print("無法讀取資料")
            return

        n = len(numbers)
        print(f"目標: {target}，共 {n} 筆金額")
        print("=" * 40)

        t0 = time.time()
        s_dp, c_dp = solve_dp(target, numbers)
        print(f"[DP]  結果: {s_dp}  差額: {target - s_dp}  耗時: {time.time() - t0:.4f} 秒")
        print(f"  組合: {c_dp}")
        print("-" * 40)

        if n > BRUTE_FORCE_LIMIT:
            print(f"[暴力法] 略過（N={n} > {BRUTE_FORCE_LIMIT}，計算量過大）")
        else:
            t0 = time.time()
            s_bf, c_bf = solve_brute_force(target, numbers)
            print(f"[BF]  結果: {s_bf}  差額: {target - s_bf}  耗時: {time.time() - t0:.4f} 秒")
            match = "相符" if s_dp == s_bf else "不符！"
            print(f"  兩法結果{match}")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _InvoicePanel(parent)


class _InvoicePanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.file_var = tk.StringVar(value="price.txt")
        self.target_var = tk.StringVar()
        self.numbers_var = tk.StringVar()
        self._build()

    def _build(self):
        ttk.Label(self, text="發票湊數小幫手", font=("", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self, text="找出最接近目標金額的金額組合", foreground="gray").pack()

        # 讀取檔案
        frame_file = ttk.LabelFrame(self, text="從檔案讀取", padding=10)
        frame_file.pack(fill="x", padx=20, pady=10)
        grid = ttk.Frame(frame_file)
        grid.pack(fill="x")
        ttk.Label(grid, text="price.txt:", width=10).grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.file_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse).grid(row=0, column=2)
        ttk.Button(grid, text="載入", command=self._load_file).grid(row=0, column=3, padx=(5, 0))
        grid.columnconfigure(1, weight=1)

        ttk.Label(self, text="或手動輸入（第一行為目標，其餘為金額，每行一個）：", foreground="gray").pack(anchor="w", padx=20, pady=(8, 2))

        frame_input = ttk.LabelFrame(self, text="手動輸入", padding=8)
        frame_input.pack(fill="x", padx=20)
        ttk.Label(frame_input, text="目標金額:").pack(anchor="w")
        ttk.Entry(frame_input, textvariable=self.target_var).pack(fill="x", pady=2)
        ttk.Label(frame_input, text="金額清單（每行一個數字）:").pack(anchor="w", pady=(5, 0))
        self.txt_numbers = scrolledtext.ScrolledText(frame_input, height=5, font=("Consolas", 10))
        self.txt_numbers.pack(fill="x", pady=2)

        self.btn_run = ttk.Button(self, text="開始計算", command=self._run)
        self.btn_run.pack(pady=10)

        result_frame = ttk.LabelFrame(self, text="計算結果", padding=8)
        result_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.txt_result = scrolledtext.ScrolledText(result_frame, state="disabled", font=("Consolas", 10))
        self.txt_result.pack(fill="both", expand=True)

    def _browse(self):
        p = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All", "*.*")])
        if p:
            self.file_var.set(p)

    def _load_file(self):
        from tools.data.invoice_helper.invoice_lib import read_price_data
        target, numbers = read_price_data(self.file_var.get())
        if target is None:
            return messagebox.showerror("錯誤", "無法讀取檔案")
        self.target_var.set(str(target))
        self.txt_numbers.delete(1.0, "end")
        self.txt_numbers.insert("end", "\n".join(str(n) for n in numbers))

    def _run(self):
        import time
        import threading
        from tools.data.invoice_helper.invoice_lib import solve_dp, solve_brute_force

        try:
            target = int(self.target_var.get().strip())
            raw = self.txt_numbers.get(1.0, "end").strip()
            numbers = [int(x.strip()) for x in raw.splitlines() if x.strip()]
        except ValueError:
            return messagebox.showerror("錯誤", "請輸入有效的數字")

        if not numbers:
            return messagebox.showwarning("警告", "請輸入金額清單")

        self.btn_run.config(state="disabled")
        self.txt_result.config(state="normal")
        self.txt_result.delete(1.0, "end")
        self.txt_result.config(state="disabled")

        def worker():
            lines = [f"目標: {target}，共 {len(numbers)} 筆\n{'='*40}"]
            t0 = time.time()
            s, c = solve_dp(target, numbers)
            lines.append(f"[DP]  結果: {s}  差額: {target - s}  耗時: {time.time() - t0:.4f} 秒")
            lines.append(f"  組合: {c}\n{'-'*40}")
            if len(numbers) > BRUTE_FORCE_LIMIT:
                lines.append(f"[暴力法] 略過（N={len(numbers)} > {BRUTE_FORCE_LIMIT}）")
            else:
                t0 = time.time()
                s_bf, c_bf = solve_brute_force(target, numbers)
                lines.append(f"[BF]  結果: {s_bf}  差額: {target - s_bf}  耗時: {time.time() - t0:.4f} 秒")
                lines.append(f"  兩法結果{'相符' if s == s_bf else '不符！'}")
            output = "\n".join(lines)

            def update():
                self.txt_result.config(state="normal")
                self.txt_result.insert("end", output)
                self.txt_result.config(state="disabled")
                self.btn_run.config(state="normal")

            self.after(0, update)

        threading.Thread(target=worker, daemon=True).start()
