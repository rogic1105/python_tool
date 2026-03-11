import argparse
import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, scrolledtext

from core.isolated_tool import IsolatedTool
from core.utils import open_folder

RUNNER = Path(__file__).parent / "runner.py"


class CrystalPathTool(IsolatedTool):
    name = "crystal_path"
    display_name = "水晶路徑動畫"
    category = "divination"
    description = "生成水晶球彩虹路徑動畫，輸出為 MP4 影片"

    venv_name = "crystal_path"
    requirements_file = "requirements.txt"
    check_imports = ["matplotlib", "numpy"]

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--output", default=".", help="輸出目錄 (預設: 當前目錄)")

    def _runner_path(self) -> Path:
        return RUNNER

    def _runner_args(self, args) -> list:
        from core.utils import FFMPEG_CMD
        return ["--output", args.output, "--ffmpeg", FFMPEG_CMD]

    def _build_panel(self, parent: tk.Widget) -> tk.Widget:
        return _CrystalPathPanel(parent, self)


class _CrystalPathPanel(ttk.Frame):
    _PREF_KEY = "crystal_path.output_dir"

    def __init__(self, parent, tool):
        super().__init__(parent)
        self.tool = tool
        from core.utils import load_pref
        self.output_var = tk.StringVar(value=load_pref(self._PREF_KEY, os.getcwd()))
        self._proc = None
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
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.output_var.get())).grid(row=0, column=3, padx=(4, 0))
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
        from core.utils import FFMPEG_CMD
        self.btn_run.config(state="disabled")
        self.log.config(state="normal")
        self.log.delete(1.0, "end")
        self.log.config(state="disabled")

        cmd = [
            self.tool.active_python, str(RUNNER),
            "--output", self.output_var.get(),
            "--ffmpeg", FFMPEG_CMD,
        ]

        def worker():
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    env=env,
                )
                for raw in self._proc.stdout:
                    line = raw.rstrip()
                    if line.startswith("LOG:"):
                        self.after(0, self._log, line[4:])
                    elif line.startswith("DONE:"):
                        self.after(0, self._log, f"[輸出] {line[5:]}")
                    elif line.startswith("ERROR:"):
                        self.after(0, self._log, f"[錯誤] {line[6:]}")
                    elif line:
                        self.after(0, self._log, line)
                self._proc.wait()
            except Exception as e:
                self.after(0, self._log, f"[例外] {e}")
            finally:
                self._proc = None
                self.after(0, lambda: self.btn_run.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()
