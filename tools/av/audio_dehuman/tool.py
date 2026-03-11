import argparse
import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, scrolledtext, messagebox

from core.isolated_tool import IsolatedTool
from core.utils import open_folder

RUNNER = Path(__file__).parent / "runner.py"
_TOOL_DIR = Path(__file__).parent


def _has_nvidia_gpu() -> bool:
    """Return True if nvidia-smi is found and reports at least one GPU."""
    import subprocess
    kwargs = dict(capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], **kwargs)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


class AudioDehumanTool(IsolatedTool):
    name = "audio_dehuman"
    display_name = "人聲去除"
    category = "av"
    description = "使用 Demucs 將音訊分離為人聲與背景音兩個檔案"

    venv_name = "demucs"
    requirements_file = "requirements.txt"
    check_imports = ["demucs"]

    def _resolve_requirements(self) -> Path:
        """
        Pick the right requirements file for the current platform:
          - macOS        → requirements-mac.txt
          - Windows+GPU  → requirements-cuda.txt  (CUDA 12.1 torch)
          - Windows+CPU  → requirements.txt
        """
        import sys as _sys
        if _sys.platform == "darwin":
            mac_req = _TOOL_DIR / "requirements-mac.txt"
            if mac_req.exists():
                return mac_req
        elif _sys.platform == "win32":
            cuda_req = _TOOL_DIR / "requirements-cuda.txt"
            if cuda_req.exists() and _has_nvidia_gpu():
                return cuda_req
        return _TOOL_DIR / "requirements.txt"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="音訊檔案路徑")
        parser.add_argument("--output", default="output", help="輸出目錄 (預設: ./output)")

    def _runner_path(self) -> Path:
        return RUNNER

    def _runner_args(self, args) -> list:
        return [args.input, "--output", args.output]

    def _build_panel(self, parent: tk.Widget) -> tk.Widget:
        return _DehumanPanel(parent, self)


class _DehumanPanel(ttk.Frame):
    _PREF_KEY = "audio_dehuman.output_dir"

    def __init__(self, parent, tool: AudioDehumanTool):
        super().__init__(parent)
        self.tool = tool
        self._proc = None
        self.input_var = tk.StringVar()
        from core.utils import load_pref
        default_out = load_pref(self._PREF_KEY, os.path.join(os.getcwd(), "output"))
        self.output_var = tk.StringVar(value=default_out)
        self._build()

    def _build(self):
        ttk.Label(self, text="人聲去除", font=("", 14, "bold")).pack(pady=(15, 5))
        gpu_ok = _has_nvidia_gpu()
        gpu_text = "GPU: NVIDIA ✓（將自動使用 CUDA）" if gpu_ok else "GPU: 未偵測到 NVIDIA GPU，使用 CPU"
        gpu_color = "#006400" if gpu_ok else "gray"
        ttk.Label(self, text=gpu_text, foreground=gpu_color, font=("", 9)).pack()

        frame_io = ttk.LabelFrame(self, text="輸入設定", padding=10)
        frame_io.pack(fill="x", padx=20, pady=10)
        grid = ttk.Frame(frame_io)
        grid.pack(fill="x")
        ttk.Label(grid, text="音訊檔案:", width=10).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse_input).grid(row=0, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.input_var.get())).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(grid, text="輸出目錄:", width=10).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="瀏覽", command=self._browse_output).grid(row=1, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.output_var.get())).grid(row=1, column=3, padx=(4, 0))
        grid.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=20, pady=5)
        self.btn_run = ttk.Button(btn_frame, text="開始分離", command=self._run)
        self.btn_run.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_cancel = ttk.Button(btn_frame, text="取消", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="right", fill="x", expand=True, padx=(3, 0))

        self.progress = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=20, pady=3)

        log_frame = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _browse_input(self):
        p = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.flac *.m4a"), ("All", "*.*")])
        if p:
            self.input_var.set(p)

    def _browse_output(self):
        p = filedialog.askdirectory()
        if p:
            self.output_var.set(p)
            from core.utils import save_pref
            save_pref(self._PREF_KEY, p)

    def _log(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _cancel(self):
        if self._proc and self._proc.poll() is None:
            if messagebox.askyesno("取消", "確定要停止嗎？"):
                self._proc.terminate()
                self.btn_cancel.config(state="disabled")

    def _run(self):
        inp = self.input_var.get()
        if not inp or not os.path.exists(inp):
            return messagebox.showerror("錯誤", "請選擇有效的輸入檔案")

        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.progress["value"] = 0
        self.log.config(state="normal")
        self.log.delete(1.0, "end")
        self.log.config(state="disabled")

        cmd = [self.tool.active_python, str(RUNNER), inp, "--output", self.output_var.get()]
        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    def _worker(self, cmd: list):
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
                elif line.startswith("PROGRESS:"):
                    parts = line[9:].split(",", 2)
                    try:
                        val = float(parts[1])
                        self.after(0, lambda v=val: self.progress.configure(value=v))
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("DONE:"):
                    self.after(0, self._log, f"輸出目錄: {line[5:]}")
                elif line.startswith("ERROR:"):
                    self.after(0, self._log, f"[錯誤] {line[6:]}")
                elif line:
                    self.after(0, self._log, line)
            self._proc.wait()
        except Exception as e:
            self.after(0, self._log, f"[例外] {e}")
        finally:
            self._proc = None
            self.after(0, lambda: [
                self.btn_run.config(state="normal"),
                self.btn_cancel.config(state="disabled"),
            ])
