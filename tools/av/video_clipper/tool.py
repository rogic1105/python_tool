import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

from core.isolated_tool import IsolatedTool
from core.utils import FFMPEG_CMD, load_pref, save_pref, open_folder

_TOOL_DIR = Path(__file__).parent
_PLAYER   = _TOOL_DIR / ("player_mac.py" if sys.platform == "darwin" else "player.py")
_RUNNER   = _TOOL_DIR / "runner.py"

_PREVIEW_W = 320
_PREVIEW_H = 180


def _find_ffprobe() -> str:
    p = shutil.which("ffprobe")
    if p:
        return p
    ff = Path(FFMPEG_CMD)
    if ff.parent != Path("."):
        candidate = ff.parent / "ffprobe"
        if candidate.exists():
            return str(candidate)
    return "ffprobe"


_FFPROBE = _find_ffprobe()


def _fmt(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    return f"{m:02d}:{s:06.3f}"


def _parse(s: str) -> float:
    s = s.strip()
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return 0.0


class VideoClipperTool(IsolatedTool):
    name         = "video_clipper"
    display_name = "影片剪裁"
    category     = "av"
    description  = "播放影片並擷取指定時間範圍片段"

    venv_name         = "video_clipper"
    requirements_file = "requirements.txt"
    check_imports     = ["sounddevice", "numpy"] if sys.platform == "darwin" else ["pygame"]

    def _resolve_requirements(self) -> Path:
        if sys.platform == "darwin":
            mac = _TOOL_DIR / "requirements-mac.txt"
            if mac.exists():
                return mac
        return _TOOL_DIR / "requirements.txt"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input",    help="輸入影片路徑")
        parser.add_argument("--start",  default="0",   help="開始時間（秒 或 HH:MM:SS.mmm）")
        parser.add_argument("--end",    required=True,  help="結束時間（秒 或 HH:MM:SS.mmm）")
        parser.add_argument("--output", "-o", default=None, help="輸出路徑")
        parser.add_argument("--reencode", action="store_true", help="精準剪裁（重新編碼）")

    def _runner_path(self) -> Path:
        return _RUNNER

    def _runner_args(self, args) -> list:
        start    = _parse(args.start)
        end      = _parse(args.end)
        src      = Path(args.input)
        out      = args.output or str(src.parent / f"{src.stem}_clip{src.suffix}")
        extra    = ["--reencode"] if args.reencode else []
        return [args.input, str(start), str(end - start), out, FFMPEG_CMD] + extra

    def _build_panel(self, parent: tk.Widget) -> tk.Widget:
        return _VideoClipperPanel(parent, self)


# ─────────────────────────────────────────────────────────────────────────────

class _VideoClipperPanel(ttk.Frame):
    _PREF_OUT = "video_clipper.output_dir"

    def __init__(self, parent, tool: VideoClipperTool):
        super().__init__(parent)
        self.tool = tool

        self._duration    = 0.0
        self._current_pos = 0.0
        self._is_playing  = False
        self._seeking     = False
        self._destroyed   = False

        self._player_proc  = None
        self._extract_proc = None

        # Frame preview state
        self._photo        = None
        self._tmp_dir      = tempfile.mkdtemp(prefix="vclipper_")
        self._tmp_frame    = os.path.join(self._tmp_dir, "frame.ppm")
        self._frame_lock   = threading.Lock()
        self._frame_pending = False
        self._pending_ts   = 0.0
        self._frame_timer  = None   # after() id for playback frame updates

        self._build()

    # ──────────────────────────── UI ────────────────────────────

    def _build(self):
        ttk.Label(self, text="影片剪裁", font=("", 14, "bold")).pack(pady=(15, 2))
        ttk.Label(self, text="播放影片，標記範圍，擷取片段輸出",
                  foreground="gray").pack(pady=(0, 10))

        # ── 1. 輸入 + 輸出（同一框）──
        io = ttk.LabelFrame(self, text="輸入 / 輸出", padding=8)
        io.pack(fill="x", padx=20, pady=(0, 8))

        frow = ttk.Frame(io)
        frow.pack(fill="x", pady=(0, 4))
        ttk.Label(frow, text="影片:", width=5).pack(side="left")
        self.file_var = tk.StringVar()
        ttk.Entry(frow, textvariable=self.file_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(frow, text="開啟", command=self._browse_file).pack(side="left")
        ttk.Button(frow, text="📂", command=lambda: open_folder(self.file_var.get())).pack(side="left", padx=(4, 0))

        orow = ttk.Frame(io)
        orow.pack(fill="x", pady=(0, 4))
        ttk.Label(orow, text="輸出:", width=5).pack(side="left")
        self.out_var = tk.StringVar(value=load_pref(self._PREF_OUT, os.getcwd()))
        ttk.Entry(orow, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(orow, text="選擇", command=self._browse_output).pack(side="left")
        ttk.Button(orow, text="📂", command=lambda: open_folder(self.out_var.get())).pack(side="left", padx=(4, 0))

        self.reencode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(io, text="精準剪裁（重新編碼，較慢但無關鍵幀偏移）",
                        variable=self.reencode_var).pack(anchor="w")

        # ── 2. 播放器（開始/結束時間在右上角）──
        pl = ttk.LabelFrame(self, text="播放器", padding=8)
        pl.pack(fill="x", padx=20, pady=(0, 8))

        # 播放控制列（左：▶⏹ 時間；右：開始/結束時間輸入）
        ctrl = ttk.Frame(pl)
        ctrl.pack(fill="x")

        # 左側小播放鍵 + 時間；右側整合標記＋時間輸入
        ctrl_left = ttk.Frame(ctrl)
        ctrl_left.pack(side="left")
        self.play_btn = ttk.Button(ctrl_left, text="▶", width=2,
                                   command=self._toggle_play, state="disabled")
        self.play_btn.pack(side="left")
        self.stop_btn = ttk.Button(ctrl_left, text="⏹", width=2,
                                   command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(3, 0))
        self.time_lbl = ttk.Label(ctrl_left, text="00:00.000 / 00:00.000")
        self.time_lbl.pack(side="left", padx=10)

        ctrl_right = ttk.Frame(ctrl)
        ctrl_right.pack(side="right")
        ttk.Button(ctrl_right, text="⬅ 設為開始", command=self._mark_start).pack(side="left")
        self.start_var = tk.StringVar(value="00:00.000")
        ttk.Entry(ctrl_right, textvariable=self.start_var, width=9).pack(side="left", padx=(3, 12))
        ttk.Button(ctrl_right, text="設為結束 ➡", command=self._mark_end).pack(side="left")
        self.end_var = tk.StringVar(value="00:00.000")
        ttk.Entry(ctrl_right, textvariable=self.end_var, width=9).pack(side="left", padx=(3, 0))

        # 進度條
        self.seek_var = tk.DoubleVar(value=0.0)
        self.seek_bar = ttk.Scale(pl, from_=0, to=100, orient="horizontal",
                                  variable=self.seek_var, command=self._on_seek_move)
        self.seek_bar.pack(fill="x", pady=(8, 6))
        self.seek_bar.bind("<ButtonPress-1>",   self._on_seek_press)
        self.seek_bar.bind("<ButtonRelease-1>", self._on_seek_release)

        # 擷取按鈕置中
        self.extract_btn = ttk.Button(pl, text="擷取片段", command=self._extract)
        self.extract_btn.pack()

        # ── 4. 執行紀錄 + 預覽（同一排，1:1）──
        bottom = ttk.Frame(self)
        bottom.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        bottom.columnconfigure(0, weight=1, uniform="half")
        bottom.columnconfigure(1, weight=1, uniform="half")
        bottom.rowconfigure(0, weight=1)

        lf = ttk.LabelFrame(bottom, text="執行紀錄", padding=8)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)
        self.log = scrolledtext.ScrolledText(lf, state="disabled", font=("Consolas", 9))
        self.log.grid(row=0, column=0, sticky="nsew")

        pv = ttk.LabelFrame(bottom, text="預覽", padding=4)
        pv.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        self.canvas = tk.Canvas(pv, bg="#0f0a14", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(_PREVIEW_W // 2, _PREVIEW_H // 2,
                                text="請選擇影片檔案", fill="#555555", font=("", 12),
                                tags="placeholder")

    # ──────────────────────────── 檔案 ────────────────────────────

    def _browse_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("影片檔案", "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.ts *.m4v"),
                       ("所有檔案", "*.*")]
        )
        if path:
            self.file_var.set(path)
            self._load_video(path)

    def _load_video(self, path: str):
        self._stop()
        self._duration    = 0.0
        self._current_pos = 0.0
        self._is_playing  = False
        self.play_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")

        self._kill_player()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [self.tool.active_python, str(_PLAYER), path, FFMPEG_CMD]
        try:
            self._player_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", env=env,
            )
        except Exception as e:
            self._log(f"無法啟動播放器：{e}")
            return

        threading.Thread(target=self._read_player, daemon=True).start()
        self._log(f"正在載入：{Path(path).name}")
        # 預覽第一幀
        self._request_frame(0.0)

    # ──────────────────────────── 播放器 stdout ────────────────────────────

    def _read_player(self):
        for raw in self._player_proc.stdout:
            if self._destroyed:
                break
            line = raw.strip()
            if line.startswith("DUR:"):
                self.after(0, self._on_player_ready, float(line[4:]))
            elif line.startswith("POS:"):
                pos = float(line[4:])
                self._current_pos = pos
                if not self._seeking:
                    self.after(0, self._sync_seek, pos)
            elif line.startswith("ERROR:"):
                self.after(0, self._log, f"播放器：{line[6:]}")
        if not self._destroyed:
            self.after(0, self._on_player_stopped)

    def _on_player_ready(self, dur: float):
        self._duration = dur
        self.seek_bar.config(to=max(dur, 1.0))
        self.seek_var.set(0.0)
        self.end_var.set(_fmt(dur))
        self._update_time_lbl()
        self.play_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        self._log(f"已載入：{Path(self.file_var.get()).name}（{_fmt(dur)}）")

    def _on_player_stopped(self):
        self._is_playing = False
        self._stop_frame_timer()
        self.play_btn.config(text="▶")

    def _sync_seek(self, pos: float):
        self.seek_var.set(pos)
        self._update_time_lbl()

    # ──────────────────────────── 播放控制 ────────────────────────────

    def _toggle_play(self):
        if not self._player_proc or self._player_proc.poll() is not None:
            return
        if self._is_playing:
            self._send_player("PAUSE")
            self._is_playing = False
            self._stop_frame_timer()
            self.play_btn.config(text="▶")
        else:
            self._send_player("PLAY")
            self._is_playing = True
            self._start_frame_timer()
            self.play_btn.config(text="⏸")

    def _stop(self):
        self._send_player("STOP")
        self._is_playing = False
        self._current_pos = 0.0
        self._stop_frame_timer()
        self.play_btn.config(text="▶")
        self.seek_var.set(0.0)
        self._update_time_lbl()

    # ──────────────────────────── 進度條 ────────────────────────────

    def _on_seek_press(self, _event):
        self._seeking = True
        if self._is_playing:
            self._send_player("PAUSE")
            self._stop_frame_timer()

    def _on_seek_move(self, val):
        self._current_pos = float(val)
        self._update_time_lbl()

    def _on_seek_release(self, _event):
        self._seeking = False
        pos = float(self.seek_var.get())
        self._current_pos = pos
        self._send_player(f"SEEK {pos:.3f}")
        self._request_frame(pos)
        if self._is_playing:
            self._send_player("PLAY")
            self._start_frame_timer()
        self._update_time_lbl()

    # ──────────────────────────── 幀預覽 ────────────────────────────

    def _start_frame_timer(self):
        self._stop_frame_timer()
        self._frame_timer = self.after(200, self._frame_tick)

    def _stop_frame_timer(self):
        if self._frame_timer is not None:
            self.after_cancel(self._frame_timer)
            self._frame_timer = None

    def _frame_tick(self):
        if self._is_playing and not self._destroyed:
            self._request_frame(self._current_pos)
            self._frame_timer = self.after(200, self._frame_tick)

    def _request_frame(self, timestamp: float):
        with self._frame_lock:
            self._pending_ts = timestamp
            if self._frame_pending:
                return
            self._frame_pending = True
        threading.Thread(target=self._frame_thread, daemon=True).start()

    def _frame_thread(self):
        while True:
            with self._frame_lock:
                ts = self._pending_ts
            self._render_frame(ts)
            with self._frame_lock:
                if self._pending_ts == ts:
                    self._frame_pending = False
                    return

    def _render_frame(self, timestamp: float):
        src = self.file_var.get()
        if not src or self._destroyed:
            return
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [
            FFMPEG_CMD, "-ss", f"{timestamp:.3f}", "-i", src,
            "-vframes", "1",
            "-vf", (f"scale={_PREVIEW_W}:{_PREVIEW_H}:force_original_aspect_ratio=decrease,"
                    f"pad={_PREVIEW_W}:{_PREVIEW_H}:(ow-iw)/2:(oh-ih)/2:color=#0f0a14"),
            "-f", "image2", "-vcodec", "ppm", "-y", self._tmp_frame,
        ]
        result = subprocess.run(cmd, capture_output=True, env=env)
        if result.returncode == 0 and os.path.exists(self._tmp_frame) and not self._destroyed:
            self.after(0, self._display_frame)

    def _display_frame(self):
        if self._destroyed:
            return
        try:
            photo = tk.PhotoImage(file=self._tmp_frame)
            self._photo = photo
            self.canvas.delete("all")
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            self.canvas.create_image(cw // 2, ch // 2, anchor="center", image=photo)
        except Exception:
            pass

    # ──────────────────────────── 標記 ────────────────────────────

    def _mark_start(self):
        self.start_var.set(_fmt(self._current_pos))

    def _mark_end(self):
        self.end_var.set(_fmt(self._current_pos))

    def _update_time_lbl(self):
        self.time_lbl.config(text=f"{_fmt(self._current_pos)} / {_fmt(self._duration)}")

    # ──────────────────────────── 輸出 ────────────────────────────

    def _browse_output(self):
        p = filedialog.askdirectory()
        if p:
            self.out_var.set(p)
            save_pref(self._PREF_OUT, p)

    # ──────────────────────────── 擷取 ────────────────────────────

    def _extract(self):
        src = self.file_var.get()
        if not src:
            self._log("請先選擇影片")
            return
        try:
            start = _parse(self.start_var.get())
            end   = _parse(self.end_var.get())
        except ValueError:
            self._log("時間格式錯誤，請使用 MM:SS.mmm 或 HH:MM:SS.mmm")
            return
        if end <= start:
            self._log("結束時間必須大於開始時間")
            return

        src_path = Path(src)
        s_tag = self.start_var.get().replace(":", "-")
        e_tag = self.end_var.get().replace(":", "-")
        out_path = Path(self.out_var.get()) / f"{src_path.stem}_{s_tag}_to_{e_tag}{src_path.suffix}"
        extra = ["--reencode"] if self.reencode_var.get() else []

        self.extract_btn.config(state="disabled")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [self.tool.active_python, str(_RUNNER),
               src, str(start), str(end - start), str(out_path), FFMPEG_CMD] + extra
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

    # ──────────────────────────── 紀錄 ────────────────────────────

    def _log(self, msg: str):
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.config(state="disabled")
        self.after(0, _do)

    # ──────────────────────────── 清理 ────────────────────────────

    def _send_player(self, cmd: str):
        if self._player_proc and self._player_proc.poll() is None:
            try:
                self._player_proc.stdin.write(cmd + "\n")
                self._player_proc.stdin.flush()
            except Exception:
                pass

    def _kill_player(self):
        self._stop_frame_timer()
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
        try:
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        except Exception:
            pass
        super().destroy()
