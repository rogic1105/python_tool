import argparse
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

from core.isolated_tool import IsolatedTool
from core.utils import FFMPEG_CMD, load_pref, save_pref, open_folder

_TOOL_DIR = Path(__file__).parent
PLAYER = _TOOL_DIR / ("player_mac.py" if sys.platform == "darwin" else "player.py")
RUNNER = _TOOL_DIR / "runner.py"


def _find_ffprobe() -> str:
    p = shutil.which("ffprobe")
    if p:
        return p
    ff = Path(FFMPEG_CMD)
    if ff.parent != Path("."):
        name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        candidate = ff.parent / name
        if candidate.exists():
            return str(candidate)
    return "ffprobe"


_FFPROBE = _find_ffprobe()


def _fmt(sec: float) -> str:
    m = int(sec // 60)
    s = sec % 60
    return f"{m:02d}:{s:06.3f}"


def _parse(s: str) -> float:
    s = s.strip()
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(m) * 60 + float(sec)
    return float(s)


class AudioClipperTool(IsolatedTool):
    name = "audio_clipper"
    display_name = "音檔剪裁"
    category = "av"
    description = "播放音檔並擷取指定時間範圍片段（含播放器與進度條）"

    venv_name = "audio_clipper"
    requirements_file = "requirements.txt"
    check_imports = ["sounddevice", "numpy"] if sys.platform == "darwin" else ["pygame"]

    def _resolve_requirements(self) -> Path:
        if sys.platform == "darwin":
            mac = _TOOL_DIR / "requirements-mac.txt"
            if mac.exists():
                return mac
        return _TOOL_DIR / "requirements.txt"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="輸入音檔路徑")
        parser.add_argument("--start", default="0", help="開始時間（秒 或 MM:SS.mmm）")
        parser.add_argument("--end", required=True, help="結束時間（秒 或 MM:SS.mmm）")
        parser.add_argument("--output", "-o", default=None, help="輸出路徑（預設：自動命名）")

    def _runner_path(self) -> Path:
        return RUNNER

    def _runner_args(self, args) -> list:
        start = _parse(args.start)
        end = _parse(args.end)
        src = Path(args.input)
        out = args.output or str(
            src.parent / f"{src.stem}_{args.start.replace(':', '-')}_to_{args.end.replace(':', '-')}{src.suffix}"
        )
        return [args.input, str(start), str(end - start), out, FFMPEG_CMD]

    def _build_panel(self, parent: tk.Widget) -> tk.Widget:
        return _AudioClipperPanel(parent, self)


class _AudioClipperPanel(ttk.Frame):
    _PREF_OUT = "audio_clipper.output_dir"

    def __init__(self, parent, tool: AudioClipperTool):
        super().__init__(parent)
        self.tool = tool

        self._duration = 0.0
        self._current_pos = 0.0
        self._is_playing = False
        self._seeking = False

        self._player_proc = None
        self._extract_proc = None
        self._destroyed = False

        self._build()

    # ─────────────────────── UI ───────────────────────

    def _build(self):
        ttk.Label(self, text="音檔剪裁", font=("", 14, "bold")).pack(pady=(15, 2))
        ttk.Label(self, text="播放音檔，標記範圍，擷取片段輸出", foreground="gray").pack(pady=(0, 10))

        # ── 音檔 ──
        ff = ttk.LabelFrame(self, text="音檔", padding=8)
        ff.pack(fill="x", padx=20, pady=(0, 8))
        frow = ttk.Frame(ff)
        frow.pack(fill="x")
        self.file_var = tk.StringVar()
        ttk.Entry(frow, textvariable=self.file_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(frow, text="開啟檔案", command=self._browse_file).pack(side="left")
        ttk.Button(frow, text="📂", command=lambda: open_folder(self.file_var.get())).pack(side="left", padx=(4, 0))

        # ── 播放器 ──
        pf = ttk.LabelFrame(self, text="播放器", padding=8)
        pf.pack(fill="x", padx=20, pady=(0, 8))

        ctrl = ttk.Frame(pf)
        ctrl.pack(fill="x")
        self.play_btn = ttk.Button(ctrl, text="▶", width=3, command=self._toggle_play, state="disabled")
        self.play_btn.pack(side="left")
        self.stop_btn = ttk.Button(ctrl, text="⏹", width=3, command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(4, 0))
        self.time_lbl = ttk.Label(ctrl, text="00:00.000 / 00:00.000")
        self.time_lbl.pack(side="left", padx=12)

        # 進度條
        self.seek_var = tk.DoubleVar(value=0.0)
        self.seek_bar = ttk.Scale(pf, from_=0, to=100, orient="horizontal",
                                  variable=self.seek_var, command=self._on_seek_move)
        self.seek_bar.pack(fill="x", pady=(8, 4))
        self.seek_bar.bind("<ButtonPress-1>", self._on_seek_press)
        self.seek_bar.bind("<ButtonRelease-1>", self._on_seek_release)

        # 標記按鈕
        mbtn = ttk.Frame(pf)
        mbtn.pack(fill="x")
        ttk.Button(mbtn, text="⬅ 設為開始時間", command=self._mark_start).pack(side="left")
        self.start_indicator = ttk.Label(mbtn, text="開始：--:--.---", foreground="#2288cc")
        self.start_indicator.pack(side="left", padx=12)
        self.end_indicator = ttk.Label(mbtn, text="結束：--:--.---", foreground="#cc4422")
        self.end_indicator.pack(side="right", padx=12)
        ttk.Button(mbtn, text="設為結束時間 ➡", command=self._mark_end).pack(side="right")

        # ── 剪裁範圍 ──
        rf = ttk.LabelFrame(self, text="剪裁範圍（可手動輸入）", padding=8)
        rf.pack(fill="x", padx=20, pady=(0, 8))
        rrow = ttk.Frame(rf)
        rrow.pack()
        ttk.Label(rrow, text="開始時間:").pack(side="left")
        self.start_var = tk.StringVar(value="00:00.000")
        ttk.Entry(rrow, textvariable=self.start_var, width=12).pack(side="left", padx=5)
        ttk.Label(rrow, text="結束時間:").pack(side="left", padx=(20, 0))
        self.end_var = tk.StringVar(value="00:00.000")
        ttk.Entry(rrow, textvariable=self.end_var, width=12).pack(side="left", padx=5)

        # ── 輸出 ──
        of = ttk.LabelFrame(self, text="輸出", padding=8)
        of.pack(fill="x", padx=20, pady=(0, 8))
        orow = ttk.Frame(of)
        orow.pack(fill="x")
        ttk.Label(orow, text="輸出目錄:").pack(side="left")
        self.out_var = tk.StringVar(value=load_pref(self._PREF_OUT, os.getcwd()))
        ttk.Entry(orow, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(orow, text="選擇", command=self._browse_output).pack(side="left")
        ttk.Button(orow, text="📂", command=lambda: open_folder(self.out_var.get())).pack(side="left", padx=(4, 0))

        # ── 擷取按鈕 ──
        self.extract_btn = ttk.Button(self, text="擷取音檔", command=self._extract)
        self.extract_btn.pack(pady=8)

        # ── 執行紀錄 ──
        lf = ttk.LabelFrame(self, text="執行紀錄", padding=8)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log = scrolledtext.ScrolledText(lf, state="disabled", font=("Consolas", 9), height=5)
        self.log.pack(fill="both", expand=True)

    # ─────────────────────── 檔案 ───────────────────────

    def _browse_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("音訊檔案", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus"),
                       ("所有檔案", "*.*")]
        )
        if path:
            self.file_var.set(path)
            self._load_audio(path)

    def _load_audio(self, path):
        self._stop()
        self._duration = 0.0
        self._current_pos = 0.0
        self._is_playing = False
        self.play_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")

        # Spawn player subprocess
        self._kill_player()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [self.tool.active_python, str(PLAYER), path, FFMPEG_CMD]
        try:
            self._player_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                env=env,
            )
        except Exception as e:
            self._log(f"無法啟動播放器：{e}")
            return

        threading.Thread(target=self._read_player, daemon=True).start()
        self._log(f"正在載入：{Path(path).name}")

    def _read_player(self):
        """Background thread: reads player subprocess stdout."""
        for raw in self._player_proc.stdout:
            if self._destroyed:
                break
            line = raw.strip()
            if line.startswith("DUR:"):
                dur = float(line[4:])
                self.after(0, self._on_player_ready, dur)
            elif line.startswith("POS:"):
                pos = float(line[4:])
                self._current_pos = pos
                if not self._seeking:
                    self.after(0, self._sync_seek, pos)
            elif line.startswith("ERROR:"):
                self.after(0, self._log, f"播放器：{line[6:]}")
        # Process ended — reset play button
        if not self._destroyed:
            self.after(0, self._on_player_stopped)

    def _on_player_ready(self, dur: float):
        self._duration = dur
        self.seek_bar.config(to=max(dur, 1.0))
        self.seek_var.set(0.0)
        self.end_var.set(_fmt(dur))
        self.end_indicator.config(text=f"結束：{_fmt(dur)}")
        self._update_time_lbl()
        self.play_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        self._log(f"已載入：{Path(self.file_var.get()).name}（{_fmt(dur)}）")

    def _on_player_stopped(self):
        self._is_playing = False
        self.play_btn.config(text="▶")

    def _sync_seek(self, pos: float):
        self.seek_var.set(pos)
        self._update_time_lbl()

    # ─────────────────────── 播放控制 ───────────────────────

    def _toggle_play(self):
        if not self._player_proc or self._player_proc.poll() is not None:
            return
        if self._is_playing:
            self._send_player("PAUSE")
            self._is_playing = False
            self.play_btn.config(text="▶")
        else:
            self._send_player("PLAY")
            self._is_playing = True
            self.play_btn.config(text="⏸")

    def _stop(self):
        self._send_player("STOP")
        self._is_playing = False
        self._current_pos = 0.0
        self.play_btn.config(text="▶")
        self.seek_var.set(0.0)
        self._update_time_lbl()

    # ─────────────────────── 進度條 ───────────────────────

    def _on_seek_press(self, event):
        self._seeking = True
        if self._is_playing:
            self._send_player("PAUSE")

    def _on_seek_move(self, val):
        self._current_pos = float(val)
        self._update_time_lbl()

    def _on_seek_release(self, event):
        self._seeking = False
        new_pos = float(self.seek_var.get())
        self._current_pos = new_pos
        self._send_player(f"SEEK {new_pos:.3f}")
        if self._is_playing:
            self._send_player("PLAY")
        self._update_time_lbl()

    # ─────────────────────── 標記 ───────────────────────

    def _mark_start(self):
        self.start_var.set(_fmt(self._current_pos))
        self.start_indicator.config(text=f"開始：{_fmt(self._current_pos)}")

    def _mark_end(self):
        self.end_var.set(_fmt(self._current_pos))
        self.end_indicator.config(text=f"結束：{_fmt(self._current_pos)}")

    def _update_time_lbl(self):
        self.time_lbl.config(text=f"{_fmt(self._current_pos)} / {_fmt(self._duration)}")

    # ─────────────────────── 輸出 ───────────────────────

    def _browse_output(self):
        p = filedialog.askdirectory()
        if p:
            self.out_var.set(p)
            save_pref(self._PREF_OUT, p)

    # ─────────────────────── 擷取 ───────────────────────

    def _extract(self):
        src = self.file_var.get()
        if not src:
            self._log("請先選擇音檔")
            return
        try:
            start = _parse(self.start_var.get())
            end = _parse(self.end_var.get())
        except ValueError:
            self._log("時間格式錯誤，請使用 MM:SS.mmm")
            return
        if end <= start:
            self._log("結束時間必須大於開始時間")
            return

        src_path = Path(src)
        s_tag = self.start_var.get().replace(":", "-")
        e_tag = self.end_var.get().replace(":", "-")
        out_path = Path(self.out_var.get()) / f"{src_path.stem}_{s_tag}_to_{e_tag}{src_path.suffix}"

        self.extract_btn.config(state="disabled")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [self.tool.active_python, str(RUNNER),
               src, str(start), str(end - start), str(out_path), FFMPEG_CMD]
        threading.Thread(target=self._run_extract, args=(cmd, str(out_path)), daemon=True).start()

    def _run_extract(self, cmd: list, out_path: str):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
            )
            for raw in proc.stdout:
                line = raw.strip()
                if line.startswith("LOG:"):
                    self.after(0, self._log, line[4:])
                elif line.startswith("DONE:"):
                    self.after(0, self._log, f"完成：{line[5:]}")
                    self.after(0, lambda p=out_path: open_folder(p))
                elif line.startswith("ERROR:"):
                    self.after(0, self._log, f"錯誤：{line[6:]}")
                elif line:
                    self.after(0, self._log, line)
            proc.wait()
        except Exception as e:
            self.after(0, self._log, f"錯誤：{e}")
        finally:
            self.after(0, lambda: self.extract_btn.config(state="normal"))

    # ─────────────────────── 紀錄 ───────────────────────

    def _log(self, msg: str):
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.config(state="disabled")
        self.after(0, _do)

    # ─────────────────────── 清理 ───────────────────────

    def _send_player(self, cmd: str):
        if self._player_proc and self._player_proc.poll() is None:
            try:
                self._player_proc.stdin.write(cmd + "\n")
                self._player_proc.stdin.flush()
            except Exception:
                pass

    def _kill_player(self):
        if self._player_proc and self._player_proc.poll() is None:
            self._send_player("QUIT")
            try:
                self._player_proc.terminate()
            except Exception:
                pass
        self._player_proc = None

    def destroy(self):
        self._destroyed = True
        self._kill_player()
        super().destroy()
