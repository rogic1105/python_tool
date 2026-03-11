import argparse
import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from core.base_tool import BaseTool
from core.utils import open_folder


class GetFramesTool(BaseTool):
    name = "get_frames"
    display_name = "取得首尾幀"
    category = "av"
    description = "從影片中擷取第一幀與最後一幀，儲存為 PNG 圖片"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="影片檔案路徑")
        parser.add_argument("--prefix", default=None, help="輸出檔案前綴 (預設: 與輸入同名)")
        parser.add_argument("--output-dir", default=None, help="輸出目錄 (預設: 與影片同目錄)")

    def run_cli(self, args) -> None:
        from tools.av.get_frames.core import get_first_last_frames
        success = get_first_last_frames(args.input, args.prefix, args.output_dir)
        if not success:
            print("[失敗] 擷取幀時發生錯誤")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _GetFramesPanel(parent)


class _GetFramesPanel(ttk.Frame):
    _PREF_KEY = "get_frames.output_dir"

    def __init__(self, parent):
        super().__init__(parent)
        from core.utils import load_pref
        self.file_var = tk.StringVar()
        self.output_var = tk.StringVar(value=load_pref(self._PREF_KEY, ""))
        self._build()

    def _build(self):
        ttk.Label(self, text="取得首尾幀", font=("", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self, text="從影片中擷取第一幀與最後一幀為 PNG", foreground="gray").pack()

        frame = ttk.LabelFrame(self, text="設定", padding=10)
        frame.pack(fill="x", padx=20, pady=15)
        grid = ttk.Frame(frame)
        grid.pack(fill="x")

        ttk.Label(grid, text="影片檔案:", width=10).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.file_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse_file).grid(row=0, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.file_var.get())).grid(row=0, column=3, padx=(4, 0))

        ttk.Label(grid, text="輸出目錄:", width=10).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse_output).grid(row=1, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.output_var.get())).grid(row=1, column=3, padx=(4, 0))
        ttk.Label(grid, text="(留空與影片同目錄)", foreground="gray").grid(row=1, column=4, sticky="w", padx=4)

        grid.columnconfigure(1, weight=1)

        self.btn_run = ttk.Button(self, text="擷取幀", command=self._run)
        self.btn_run.pack(pady=10)

        log_frame = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _browse_file(self):
        p = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.mov *.avi"), ("All", "*.*")])
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
        from tools.av.get_frames.core import get_first_last_frames
        f = self.file_var.get()
        if not f:
            return messagebox.showwarning("警告", "請選擇影片檔案")
        out_dir = self.output_var.get().strip() or None
        self.btn_run.config(state="disabled")

        def worker():
            success = get_first_last_frames(
                f, output_dir=out_dir,
                log_cb=lambda m: self.after(0, self._log, m),
            )
            msg = "擷取完成！" if success else "擷取失敗，請查看紀錄"
            self.after(0, lambda: [messagebox.showinfo("結果", msg), self.btn_run.config(state="normal")])

        threading.Thread(target=worker, daemon=True).start()
