import argparse
import os
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

from core.isolated_tool import IsolatedTool
from core.utils import FFMPEG_CMD, load_pref, save_pref, open_folder

_TOOL_DIR = Path(__file__).parent
_RUNNER   = _TOOL_DIR / "runner.py"


class AudioVizTool(IsolatedTool):
    name         = "audio_viz"
    display_name = "音訊動態"
    category     = "media"
    description  = "將音訊頻譜渲染成彩虹柱狀動態影片"

    venv_name         = "audio_viz"
    requirements_file = "requirements.txt"
    check_imports     = ["numpy", "librosa", "cv2", "moviepy"]

    def _resolve_requirements(self) -> Path:
        if sys.platform == "darwin":
            mac = _TOOL_DIR / "requirements-mac.txt"
            if mac.exists():
                return mac
        return _TOOL_DIR / "requirements.txt"

    def _runner_path(self) -> Path:
        return _RUNNER

    def _runner_args(self, args) -> list:
        out = args.output or str(Path(args.input).with_suffix(".mp4"))
        return [args.input, out]

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="輸入音訊檔案路徑")
        parser.add_argument("--output", "-o", default=None, help="輸出影片路徑（預設：同名 .mp4）")

    def _build_panel(self, parent: tk.Widget) -> tk.Widget:
        return _AudioVizPanel(parent, self)


class _AudioVizPanel(ttk.Frame):
    _PREF_OUT = "audio_viz.output_dir"

    def __init__(self, parent, tool: AudioVizTool):
        super().__init__(parent)
        self.tool = tool
        self._proc = None
        self._running = False
        self._build()

    def _build(self):
        ttk.Label(self, text="音訊動態", font=("", 14, "bold")).pack(pady=(15, 2))
        ttk.Label(self, text="將音訊頻譜渲染成彩虹柱狀動態影片", foreground="gray").pack(pady=(0, 10))

        # ── 輸入音訊 ──
        inf = ttk.LabelFrame(self, text="輸入音訊", padding=8)
        inf.pack(fill="x", padx=20, pady=(0, 8))
        irow = ttk.Frame(inf)
        irow.pack(fill="x")
        self.input_var = tk.StringVar()
        ttk.Entry(irow, textvariable=self.input_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(irow, text="選擇", command=self._browse_input).pack(side="left")
        ttk.Button(irow, text="📂", command=lambda: open_folder(self.input_var.get())).pack(side="left", padx=(4, 0))

        # ── 輸出目錄 ──
        of = ttk.LabelFrame(self, text="輸出目錄", padding=8)
        of.pack(fill="x", padx=20, pady=(0, 8))
        orow = ttk.Frame(of)
        orow.pack(fill="x")
        self.out_var = tk.StringVar(value=load_pref(self._PREF_OUT, os.getcwd()))
        ttk.Entry(orow, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(orow, text="選擇", command=self._browse_output).pack(side="left")
        ttk.Button(orow, text="📂", command=lambda: open_folder(self.out_var.get())).pack(side="left", padx=(4, 0))

        # ── 進度條 ──
        pf = ttk.LabelFrame(self, text="進度", padding=8)
        pf.pack(fill="x", padx=20, pady=(0, 8))
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(pf, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x")
        self.progress_lbl = ttk.Label(pf, text="", foreground="gray")
        self.progress_lbl.pack(anchor="w", pady=(4, 0))

        # ── 執行按鈕 ──
        btn_row = ttk.Frame(self)
        btn_row.pack(pady=8)
        self.run_btn = ttk.Button(btn_row, text="開始渲染", command=self._run)
        self.run_btn.pack(side="left", padx=4)
        self.cancel_btn = ttk.Button(btn_row, text="取消", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)

        # ── 執行紀錄 ──
        lf = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log = scrolledtext.ScrolledText(lf, state="disabled", font=("Consolas", 9), height=8)
        self.log.pack(fill="both", expand=True)

    # ── 瀏覽 ──

    def _browse_input(self):
        path = filedialog.askopenfilename(
            filetypes=[("音訊檔案", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg"),
                       ("所有檔案", "*.*")]
        )
        if path:
            self.input_var.set(path)
            # 預設輸出目錄跟著輸入檔所在目錄
            self.out_var.set(str(Path(path).parent))

    def _browse_output(self):
        p = filedialog.askdirectory()
        if p:
            self.out_var.set(p)
            save_pref(self._PREF_OUT, p)

    # ── 執行 ──

    def _run(self):
        src = self.input_var.get().strip()
        if not src:
            self._log("請先選擇輸入音訊檔案")
            return
        if not Path(src).exists():
            self._log(f"檔案不存在：{src}")
            return

        out_dir = self.out_var.get().strip() or os.getcwd()
        out_path = str(Path(out_dir) / (Path(src).stem + "_viz.mp4"))

        self._running = True
        self.run_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress_var.set(0.0)
        self.progress_lbl.config(text="")

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [self.tool.active_python, str(_RUNNER), src, out_path]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
            )
        except Exception as e:
            self._log(f"無法啟動：{e}")
            self._set_idle()
            return

        threading.Thread(target=self._read_proc, args=(out_path,), daemon=True).start()

    def _read_proc(self, out_path: str):
        for raw in self._proc.stdout:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("LOG:"):
                self.after(0, self._log, line[4:])
            elif line.startswith("PROGRESS:"):
                parts = line[9:].split(",", 2)
                if len(parts) >= 2:
                    try:
                        pct = float(parts[1])
                        msg = parts[2] if len(parts) > 2 else ""
                        self.after(0, self._set_progress, pct, msg)
                    except ValueError:
                        pass
            elif line.startswith("DONE:"):
                self.after(0, self._log, f"完成：{line[5:]}")
                self.after(0, lambda p=out_path: open_folder(p))
                self.after(0, self._set_progress, 100.0, "完成")
            elif line.startswith("ERROR:"):
                self.after(0, self._log, f"錯誤：{line[6:]}")
            elif line:
                self.after(0, self._log, line)
        self._proc.wait()
        self.after(0, self._set_idle)

    def _cancel(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._log("已取消")
        self._set_idle()

    def _set_idle(self):
        self._running = False
        self._proc = None
        self.run_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

    def _set_progress(self, pct: float, msg: str):
        self.progress_var.set(pct)
        if msg:
            self.progress_lbl.config(text=msg)

    def _log(self, msg: str):
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.config(state="disabled")
        self.after(0, _do)

    def destroy(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        super().destroy()
