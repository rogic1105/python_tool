import argparse
import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from core.base_tool import BaseTool
from core.utils import SYSTEM, open_folder


class VideoToH264Tool(BaseTool):
    name = "video_to_h264"
    display_name = "影片轉 H.264"
    category = "av"
    description = "將影片轉為 H.264 MP4，自動選擇最佳加速方式（Mac/CUDA/CPU）"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="來源影片路徑")
        parser.add_argument("--quality", type=int, default=None, help="品質參數 (Mac: 0-100, CPU: CRF 0-51)")
        parser.add_argument("--output-dir", default=None, help="輸出目錄 (預設: 與輸入同目錄)")

    def run_cli(self, args) -> None:
        from tools.av.video_to_h264.core import convert_to_h264
        out = convert_to_h264(args.input, args.quality, args.output_dir)
        print(f"輸出: {out}")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _VideoToH264Panel(parent)


class _VideoToH264Panel(ttk.Frame):
    _PREF_KEY = "video_to_h264.output_dir"

    def __init__(self, parent):
        super().__init__(parent)
        self.file_var = tk.StringVar()

        from core.utils import get_best_h264_codec, load_pref
        self._codec, _ = get_best_h264_codec()

        # Quality slider range depends on codec
        if self._codec == "h264_videotoolbox":
            self._q_min, self._q_max, self._q_default = 1, 100, 65
            self._q_label = "品質"
            self._q_hint  = "越高越好 (預設 65)"
        else:
            # libx264 / h264_nvenc — CRF: lower = better quality
            self._q_min, self._q_max, self._q_default = 0, 51, 18
            self._q_label = "CRF"
            self._q_hint  = "越低越好 (預設 18)"

        self.quality_var = tk.IntVar(value=self._q_default)
        self.output_var = tk.StringVar(value=load_pref(self._PREF_KEY, ""))
        self._build()

    def _build(self):
        ttk.Label(self, text="影片轉 H.264", font=("", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self, text=f"自動偵測編碼器：{self._codec}", foreground="gray").pack()

        # File input
        frame = ttk.LabelFrame(self, text="檔案設定", padding=10)
        frame.pack(fill="x", padx=20, pady=(15, 8))
        grid = ttk.Frame(frame)
        grid.pack(fill="x")
        ttk.Label(grid, text="輸入影片:", width=10).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.file_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse).grid(row=0, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.file_var.get())).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(grid, text="輸出目錄:", width=10).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse_output).grid(row=1, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.output_var.get())).grid(row=1, column=3, padx=(4, 0))
        ttk.Label(grid, text="(留空與影片同目錄)", foreground="gray").grid(row=1, column=4, sticky="w", padx=4)
        grid.columnconfigure(1, weight=1)

        # Quality slider
        q_frame = ttk.LabelFrame(self, text=f"品質設定 ({self._q_label})", padding=10)
        q_frame.pack(fill="x", padx=20, pady=(0, 8))

        top_row = ttk.Frame(q_frame)
        top_row.pack(fill="x")
        ttk.Label(top_row, text=self._q_hint, foreground="gray").pack(side="left")
        self._q_val_lbl = ttk.Label(top_row, text=str(self._q_default), font=("Consolas", 11, "bold"), width=4, anchor="e")
        self._q_val_lbl.pack(side="right")

        scale_row = ttk.Frame(q_frame)
        scale_row.pack(fill="x", pady=(4, 0))
        ttk.Label(scale_row, text=str(self._q_min), foreground="gray").pack(side="left")
        self._scale = ttk.Scale(
            scale_row,
            from_=self._q_min, to=self._q_max,
            orient="horizontal",
            variable=self.quality_var,
            command=self._on_scale,
        )
        self._scale.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(scale_row, text=str(self._q_max), foreground="gray").pack(side="left")

        self.btn_run = ttk.Button(self, text="開始轉換", command=self._run)
        self.btn_run.pack(pady=10)

        log_frame = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _on_scale(self, _=None):
        val = int(self.quality_var.get())
        self.quality_var.set(val)          # snap to integer
        self._q_val_lbl.config(text=str(val))

    def _browse(self):
        p = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mkv *.mov *.avi"), ("All", "*.*")])
        if p:
            self.file_var.set(p)

    def _browse_output(self):
        p = filedialog.askdirectory()
        if p:
            self.output_var.set(p)
            from core.utils import save_pref
            save_pref(self._PREF_KEY, p)

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

        quality = int(self.quality_var.get())

        self.btn_run.config(state="disabled")
        self.log.config(state="normal")
        self.log.delete(1.0, "end")
        self.log.config(state="disabled")

        out_dir = self.output_var.get().strip() or None

        def worker():
            try:
                out = convert_to_h264(f, quality, out_dir, log_cb=lambda m: self.after(0, self._log, m))
                self.after(0, lambda: [messagebox.showinfo("完成", f"輸出: {out}"), self.btn_run.config(state="normal")])
            except Exception as e:
                self.after(0, lambda: [messagebox.showerror("錯誤", str(e)), self.btn_run.config(state="normal")])

        threading.Thread(target=worker, daemon=True).start()
