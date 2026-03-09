import argparse
import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from core.base_tool import BaseTool
from core.utils import SYSTEM


class VideoToH264Tool(BaseTool):
    name = "video_to_h264"
    display_name = "影片轉 H.264"
    category = "av"
    description = "將影片轉為 H.264 MP4，自動選擇最佳加速方式（Mac/CUDA/CPU）"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="來源影片路徑")
        parser.add_argument("--quality", type=int, default=None, help="品質參數 (Mac: 0-100, CPU: CRF 0-51)")

    def run_cli(self, args) -> None:
        from tools.av.video_to_h264.core import convert_to_h264
        out = convert_to_h264(args.input, args.quality)
        print(f"輸出: {out}")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _VideoToH264Panel(parent)


class _VideoToH264Panel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.file_var = tk.StringVar()
        self.quality_var = tk.StringVar(value="")
        self._build()

    def _build(self):
        from core.utils import get_best_h264_codec
        codec, _ = get_best_h264_codec()

        ttk.Label(self, text="影片轉 H.264", font=("", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self, text=f"自動偵測編碼器：{codec}", foreground="gray").pack()

        frame = ttk.LabelFrame(self, text="檔案設定", padding=10)
        frame.pack(fill="x", padx=20, pady=15)
        grid = ttk.Frame(frame)
        grid.pack(fill="x")
        ttk.Label(grid, text="輸入影片:", width=10).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.file_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse).grid(row=0, column=2)
        ttk.Label(grid, text="品質參數:", width=10).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.quality_var, width=8).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(grid, text="(留空使用預設值)", foreground="gray").grid(row=1, column=2, sticky="w")
        grid.columnconfigure(1, weight=1)

        self.btn_run = ttk.Button(self, text="開始轉換", command=self._run)
        self.btn_run.pack(pady=10)

        log_frame = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _browse(self):
        p = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mkv *.mov *.avi"), ("All", "*.*")])
        if p:
            self.file_var.set(p)

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _run(self):
        import threading
        from tools.av.video_to_h264.core import convert_to_h264
        from tkinter import messagebox

        f = self.file_var.get()
        if not f:
            return messagebox.showwarning("警告", "請選擇影片檔案")

        q_str = self.quality_var.get().strip()
        quality = int(q_str) if q_str.isdigit() else None

        self.btn_run.config(state="disabled")
        self.log.config(state="normal")
        self.log.delete(1.0, "end")
        self.log.config(state="disabled")

        def worker():
            try:
                out = convert_to_h264(f, quality, log_cb=lambda m: self.after(0, self._log, m))
                self.after(0, lambda: [messagebox.showinfo("完成", f"輸出: {out}"), self.btn_run.config(state="normal")])
            except Exception as e:
                self.after(0, lambda: [messagebox.showerror("錯誤", str(e)), self.btn_run.config(state="normal")])

        threading.Thread(target=worker, daemon=True).start()
