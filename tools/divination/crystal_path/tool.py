import argparse
import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from core.base_tool import BaseTool


class CrystalPathTool(BaseTool):
    name = "crystal_path"
    display_name = "水晶路徑動畫"
    category = "divination"
    description = "生成水晶球彩虹路徑動畫，輸出為 MP4 影片"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--output", default=".", help="輸出目錄 (預設: 當前目錄)")

    def run_cli(self, args) -> None:
        from tools.divination.crystal_path.core import generate_crystal_path_animation
        out = generate_crystal_path_animation(args.output)
        print(f"輸出: {out}")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _CrystalPathPanel(parent)


class _CrystalPathPanel(ttk.Frame):
    _PREF_KEY = "crystal_path.output_dir"

    def __init__(self, parent):
        super().__init__(parent)
        from core.utils import load_pref
        self.output_var = tk.StringVar(value=load_pref(self._PREF_KEY, os.getcwd()))
        self._build()

    def _build(self):
        ttk.Label(self, text="水晶路徑動畫", font=("", 14, "bold")).pack(pady=(20, 5))
        ttk.Label(self, text="生成六邊形水晶球彩虹軌跡動畫", foreground="gray").pack()
        ttk.Label(self, text="輸出格式：rainbow_crystal_snake.mp4", foreground="gray").pack(pady=(0, 15))

        frame = ttk.LabelFrame(self, text="輸出設定", padding=10)
        frame.pack(fill="x", padx=40, pady=10)
        grid = ttk.Frame(frame)
        grid.pack(fill="x")
        ttk.Label(grid, text="輸出目錄:", width=10).grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.output_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse).grid(row=0, column=2)
        grid.columnconfigure(1, weight=1)

        self.btn_run = ttk.Button(self, text="生成動畫", command=self._run)
        self.btn_run.pack(pady=15)

        log_frame = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        log_frame.pack(fill="both", expand=True, padx=40, pady=(0, 20))
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled", font=("Consolas", 9), height=6)
        self.log.pack(fill="both", expand=True)

    def _browse(self):
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
        from tools.divination.crystal_path.core import generate_crystal_path_animation
        self.btn_run.config(state="disabled")
        self.log.config(state="normal")
        self.log.delete(1.0, "end")
        self.log.config(state="disabled")

        def worker():
            try:
                out = generate_crystal_path_animation(
                    self.output_var.get(),
                    log_cb=lambda m: self.after(0, self._log, m),
                )
                self.after(0, self._log, f"[輸出] {out}")
            except Exception as e:
                self.after(0, self._log, f"[錯誤] {e}")
            finally:
                self.after(0, lambda: self.btn_run.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()
