import argparse
import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from core.base_tool import BaseTool
from core.utils import open_folder


class Mp4ToMp3Tool(BaseTool):
    name = "mp4_to_mp3"
    display_name = "MP4 轉 MP3"
    category = "av"
    description = "批次將 MP4/MOV 影片轉換為 320k 高品質 MP3"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--src", default="src", help="來源影片目錄 (預設: ./src)")
        parser.add_argument("--out", default="out", help="輸出 MP3 目錄 (預設: ./out)")

    def run_cli(self, args) -> None:
        from tools.av.mp4_to_mp3.core import convert_to_mp3
        result = convert_to_mp3(args.src, args.out)
        print(f"完成：轉換 {result['converted']} 個，略過 {result['skipped']} 個")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _Mp4ToMp3Panel(parent)


class _Mp4ToMp3Panel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.src_var = tk.StringVar(value=os.path.join(os.getcwd(), "src"))
        self.out_var = tk.StringVar(value=os.path.join(os.getcwd(), "out"))
        self._build()

    def _build(self):
        ttk.Label(self, text="MP4 轉 MP3", font=("", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self, text="批次將影片轉為 320k 高品質 MP3", foreground="gray").pack()

        frame = ttk.LabelFrame(self, text="目錄設定", padding=10)
        frame.pack(fill="x", padx=20, pady=15)

        grid = ttk.Frame(frame)
        grid.pack(fill="x")
        ttk.Label(grid, text="來源目錄:", width=10).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.src_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=lambda: self._browse(self.src_var)).grid(row=0, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.src_var.get())).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(grid, text="輸出目錄:", width=10).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=lambda: self._browse(self.out_var)).grid(row=1, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.out_var.get())).grid(row=1, column=3, padx=(4, 0))
        grid.columnconfigure(1, weight=1)

        self.btn_run = ttk.Button(self, text="開始轉換", command=self._run)
        self.btn_run.pack(pady=10)

        log_frame = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _browse(self, var):
        p = filedialog.askdirectory()
        if p:
            var.set(p)

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _run(self):
        import threading
        from tools.av.mp4_to_mp3.core import convert_to_mp3
        self.btn_run.config(state="disabled")
        self.log.config(state="normal")
        self.log.delete(1.0, "end")
        self.log.config(state="disabled")

        def worker():
            result = convert_to_mp3(self.src_var.get(), self.out_var.get(), log_cb=lambda m: self.after(0, self._log, m))
            self.after(0, lambda: [
                self._log(f"\n完成：轉換 {result['converted']} 個，略過 {result['skipped']} 個"),
                self.btn_run.config(state="normal"),
            ])

        threading.Thread(target=worker, daemon=True).start()
