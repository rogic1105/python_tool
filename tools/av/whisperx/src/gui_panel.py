"""WhisperX GUI Panel — runs in the main (lightweight) env.

Heavy processing is delegated to runner.py inside the whisperx venv via subprocess.
Output lines are parsed using the structured prefix protocol defined in isolated_tool.py.
"""

import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, scrolledtext, messagebox

from .config import DEFAULT_OUTPUT_DIR
from core.utils import open_folder

RUNNER = Path(__file__).parent.parent / "runner.py"

_STYLE_GRAY   = "WhisperX.Gray.Horizontal.TProgressbar"
_STYLE_YELLOW = "WhisperX.Yellow.Horizontal.TProgressbar"
_STYLE_GREEN  = "WhisperX.Green.Horizontal.TProgressbar"


class WhisperXPanel(ttk.Frame):
    def __init__(self, parent, tool):
        super().__init__(parent)
        self.tool = tool
        self.is_running = False
        self._proc = None

        self.file_path = tk.StringVar()
        from core.utils import load_pref
        self.output_path = tk.StringVar(value=load_pref("whisperx.output_dir", DEFAULT_OUTPUT_DIR))
        self.model_size = tk.StringVar(value="large-v2")
        self.language = tk.StringVar(value="zh")
        self.num_speakers = tk.IntVar(value=0)
        self.hf_token = tk.StringVar(value=load_pref("whisperx.hf_token", ""))
        self.batch_size = tk.IntVar(value=16)

        self._init_styles()
        self._build_ui()

    def _init_styles(self):
        s = ttk.Style(self)
        s.configure(_STYLE_GRAY,   background="#aaaaaa", troughcolor="#e0e0e0")
        s.configure(_STYLE_YELLOW, background="#e8c020", troughcolor="#e0e0e0")
        s.configure(_STYLE_GREEN,  background="#22aa44", troughcolor="#e0e0e0")

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=5)

        # 1. 檔案與路徑
        frame_io = ttk.LabelFrame(top, text="1. 檔案與路徑", padding=8)
        frame_io.pack(fill="x", pady=3)
        grid = ttk.Frame(frame_io)
        grid.pack(fill="x")
        ttk.Label(grid, text="輸入音檔:", width=10).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(grid, textvariable=self.file_path, state="readonly").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="選擇檔案", command=self._browse_file).grid(row=0, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.file_path.get())).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(grid, text="輸出目錄:", width=10).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(grid, textvariable=self.output_path).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(grid, text="變更目錄", command=self._browse_output).grid(row=1, column=2)
        ttk.Button(grid, text="開啟", command=lambda: open_folder(self.output_path.get())).grid(row=1, column=3, padx=(4, 0))
        grid.columnconfigure(1, weight=1)

        # 2. 參數設定
        frame_set = ttk.LabelFrame(top, text="2. 參數設定", padding=8)
        frame_set.pack(fill="x", pady=3)
        row1 = ttk.Frame(frame_set)
        row1.pack(fill="x")
        ttk.Label(row1, text="模型:").pack(side="left")
        cb_model = ttk.Combobox(row1, textvariable=self.model_size, state="readonly", width=12)
        cb_model["values"] = ("tiny", "base", "small", "medium", "large-v2", "large-v3")
        cb_model.pack(side="left", padx=5)
        ttk.Label(row1, text="語言:").pack(side="left", padx=(10, 0))
        cb_lang = ttk.Combobox(row1, textvariable=self.language, state="readonly", width=6)
        cb_lang["values"] = ("auto", "zh", "en", "ja", "ko")
        cb_lang.pack(side="left", padx=5)
        ttk.Label(row1, text="人數(0自動):").pack(side="left", padx=(10, 0))
        ttk.Entry(row1, textvariable=self.num_speakers, width=5).pack(side="left", padx=5)
        ttk.Label(row1, text="Batch:").pack(side="left", padx=(10, 0))
        ttk.Entry(row1, textvariable=self.batch_size, width=5).pack(side="left", padx=5)

        row2 = ttk.Frame(frame_set)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Label(row2, text="HF Token (語者分離):").pack(side="left")
        hf_entry = ttk.Entry(row2, textvariable=self.hf_token, show="*", width=40)
        hf_entry.pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(row2, text="儲存", command=self._save_hf_token).pack(side="left")
        ttk.Label(row2, text="留空則跳過語者分離", foreground="gray").pack(side="left", padx=(8, 0))

        # 3. 操作按鈕
        btn_frame = ttk.Frame(top)
        btn_frame.pack(fill="x", pady=6)
        self.btn_run = ttk.Button(btn_frame, text="開始執行", command=self._start)
        self.btn_run.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_cancel = ttk.Button(btn_frame, text="取消任務", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="right", fill="x", expand=True, padx=(3, 0))

        # 進度
        frame_prog = ttk.LabelFrame(self, text="執行進度", padding=8)
        frame_prog.pack(fill="x", padx=10, pady=3)
        self.lbl_p1 = ttk.Label(frame_prog, text="步驟 1: 格式轉換", foreground="gray")
        self.lbl_p1.pack(anchor="w")
        self.bar_p1 = ttk.Progressbar(frame_prog, style=_STYLE_GRAY, orient="horizontal", mode="determinate")
        self.bar_p1.pack(fill="x", pady=(0, 3))
        self.lbl_p2 = ttk.Label(frame_prog, text="步驟 2: 轉錄 + 對齊", foreground="gray")
        self.lbl_p2.pack(anchor="w")
        self.bar_p2 = ttk.Progressbar(frame_prog, style=_STYLE_GRAY, orient="horizontal", mode="determinate")
        self.bar_p2.pack(fill="x", pady=(0, 3))
        self.lbl_p3 = ttk.Label(frame_prog, text="步驟 3: 語者分離", foreground="gray")
        self.lbl_p3.pack(anchor="w")
        self.bar_p3 = ttk.Progressbar(frame_prog, style=_STYLE_GRAY, orient="horizontal", mode="determinate")
        self.bar_p3.pack(fill="x")

        # 輸出區
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=10, pady=(3, 10))
        frame_sys = ttk.LabelFrame(pw, text="系統資訊", padding=5)
        pw.add(frame_sys, weight=1)
        self.txt_sys = scrolledtext.ScrolledText(frame_sys, state="disabled", font=("Consolas", 9))
        self.txt_sys.pack(fill="both", expand=True)
        frame_content = ttk.LabelFrame(pw, text="轉錄內容", padding=5)
        pw.add(frame_content, weight=2)
        self.txt_content = scrolledtext.ScrolledText(frame_content, state="disabled", font=("", 10))
        self.txt_content.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # UI callbacks
    # ------------------------------------------------------------------

    def _browse_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("Audio/Video", "*.mp3 *.wav *.m4a *.flac *.mp4"), ("All", "*.*")]
        )
        if p:
            self.file_path.set(p)

    def _browse_output(self):
        p = filedialog.askdirectory()
        if p:
            self.output_path.set(p)
            from core.utils import save_pref
            save_pref("whisperx.output_dir", p)

    def _save_hf_token(self):
        from core.utils import save_pref
        save_pref("whisperx.hf_token", self.hf_token.get())
        self._log_sys("HF Token 已儲存")

    def _cancel(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self.btn_cancel.config(state="disabled")

    def _start(self):
        f = self.file_path.get()
        out = self.output_path.get()
        if not f or not os.path.exists(f):
            return messagebox.showwarning("警告", "請選擇有效的音檔")
        if not out:
            return messagebox.showwarning("警告", "請指定輸出路徑")

        self.is_running = True
        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self._reset_ui()

        try:
            spk = self.num_speakers.get()
        except Exception:
            spk = 0
        try:
            bs = self.batch_size.get()
        except Exception:
            bs = 16

        cmd = [
            self.tool.active_python, str(RUNNER),
            f,
            "--model", self.model_size.get(),
            "--language", self.language.get(),
            "--speakers", str(spk),
            "--batch-size", str(bs),
            "--output", out,
        ]
        hf = self.hf_token.get().strip()
        if hf:
            cmd += ["--hf-token", hf]

        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    # ------------------------------------------------------------------
    # Subprocess worker
    # ------------------------------------------------------------------

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
                    self._log_sys(line[4:])
                elif line.startswith("PROGRESS:"):
                    parts = line[9:].split(",", 2)
                    try:
                        stage = int(parts[0])
                        val = float(parts[1])
                        msg = parts[2] if len(parts) > 2 else None
                        self.after(0, self._update_progress, stage, val, msg)
                    except (ValueError, IndexError):
                        pass
                elif line == "CLEAR_CONTENT:":
                    self.after(0, self._clear_content)
                elif line.startswith("TEXT:"):
                    self._log_content(line[5:])
                elif line.startswith("DONE:"):
                    srt = line[5:]
                    self.after(0, self._on_done, srt)
                elif line.startswith("ERROR:"):
                    self._log_sys(f"[錯誤] {line[6:]}")
                else:
                    if line:
                        self._log_sys(line)

            self._proc.wait()
        except Exception as e:
            self._log_sys(f"[例外] {e}")
        finally:
            self.is_running = False
            self._proc = None
            self.after(0, self._reset_buttons)

    # ------------------------------------------------------------------
    # UI update helpers
    # ------------------------------------------------------------------

    def _on_done(self, srt: str):
        self.is_running = False
        self._reset_buttons()
        srt = srt.strip()
        folder = os.path.dirname(srt) if srt else self.output_path.get()
        if srt and os.path.exists(srt):
            self._log_sys(f"✓ 檔案已生成: {srt}")
            open_folder(folder)
        else:
            self._log_sys(f"⚠ 找不到輸出檔案: {srt}")

    def _reset_buttons(self):
        self.btn_run.config(state="normal")
        self.btn_cancel.config(state="disabled")

    def _log_sys(self, msg: str):
        self.after(0, lambda: [
            self.txt_sys.config(state="normal"),
            self.txt_sys.insert("end", f"> {msg}\n"),
            self.txt_sys.see("end"),
            self.txt_sys.config(state="disabled"),
        ])

    def _clear_content(self):
        self.txt_content.config(state="normal")
        self.txt_content.delete(1.0, "end")
        self.txt_content.config(state="disabled")

    def _log_content(self, text: str):
        self.after(0, lambda: [
            self.txt_content.config(state="normal"),
            self.txt_content.insert("end", text + "\n"),
            self.txt_content.see("end"),
            self.txt_content.config(state="disabled"),
        ])

    def _update_progress(self, stage: int, val: float, msg: str = None):
        bar_style = _STYLE_GREEN if val >= 100 else _STYLE_YELLOW
        lbl_color = "#22aa44" if val >= 100 else "#c08000"
        if stage == 1:
            self.bar_p1.configure(style=bar_style, value=val)
            self.lbl_p1.config(foreground=lbl_color)
        elif stage == 2:
            self.bar_p2.configure(style=bar_style, value=val)
            lbl_text = "步驟 2: 轉錄 + 對齊"
            if msg and val < 100:
                lbl_text += f" - {msg}"
            self.lbl_p2.config(text=lbl_text, foreground=lbl_color)
        elif stage == 3:
            self.bar_p3.configure(style=bar_style, value=val)
            lbl_text = "步驟 3: 語者分離"
            if msg and val < 100:
                lbl_text += f" - {msg}"
            self.lbl_p3.config(text=lbl_text, foreground=lbl_color)

    def _reset_ui(self):
        for bar, lbl, text in [
            (self.bar_p1, self.lbl_p1, "步驟 1: 格式轉換"),
            (self.bar_p2, self.lbl_p2, "步驟 2: 轉錄 + 對齊"),
            (self.bar_p3, self.lbl_p3, "步驟 3: 語者分離"),
        ]:
            bar.configure(style=_STYLE_GRAY, value=0)
            lbl.config(foreground="gray", text=text)
        for txt in (self.txt_sys, self.txt_content):
            txt.config(state="normal")
            txt.delete(1.0, "end")
            txt.config(state="disabled")
