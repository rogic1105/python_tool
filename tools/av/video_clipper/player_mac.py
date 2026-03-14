"""
macOS audio-playback subprocess for video_clipper — sounddevice + ffmpeg decode.
Video frames are rendered by the panel (separate ffmpeg calls), not here.

Usage:
    python player_mac.py <video_file> <ffmpeg_path>

Stdin commands:  PLAY  PAUSE  STOP  SEEK <seconds>  QUIT
Stdout protocol: DUR:<s>  POS:<s>  LOG:<msg>  ERROR:<msg>
"""
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

file_path = sys.argv[1]
ffmpeg    = sys.argv[2] if len(sys.argv) > 2 else "ffmpeg"

# Derive ffprobe from ffmpeg directory
_ffprobe_candidate = Path(ffmpeg).parent / "ffprobe"
ffprobe = str(_ffprobe_candidate) if _ffprobe_candidate.exists() else (shutil.which("ffprobe") or "ffprobe")

SAMPLE_RATE = 44100
CHANNELS    = 2

print("LOG:解碼音訊中...", flush=True)
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"


def _probe_duration(src: str):
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=duration",
             "-of", "csv=p=0", src],
            capture_output=True, env=env, timeout=10,
        )
        val = r.stdout.decode("utf-8", errors="replace").strip()
        return float(val) if val else None
    except Exception:
        return None


def _decode_to_f32(src: str) -> bytes:
    r = subprocess.run(
        [ffmpeg, "-i", src,
         "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
         "-vn", "pipe:1"],
        capture_output=True, env=env,
    )
    if r.returncode != 0 or len(r.stdout) == 0:
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace")[-400:])
    return r.stdout


try:
    raw = _decode_to_f32(file_path)
except Exception as first_err:
    import tempfile
    print("LOG:直接解碼失敗，嘗試先轉換為 WAV...", flush=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        conv = subprocess.run(
            [ffmpeg, "-y", "-i", file_path,
             "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), tmp.name],
            capture_output=True, env=env,
        )
        if conv.returncode != 0:
            raise RuntimeError(conv.stderr.decode("utf-8", errors="replace")[-400:])
        raw = _decode_to_f32(tmp.name)
    except Exception as e:
        print(f"ERROR:音訊解碼失敗：{e}", flush=True)
        sys.exit(1)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

try:
    audio = np.frombuffer(raw, dtype=np.float32).reshape(-1, CHANNELS)
except Exception as e:
    print(f"ERROR:音訊資料解析失敗：{e}", flush=True)
    sys.exit(1)

duration = _probe_duration(file_path) or (len(audio) / SAMPLE_RATE)
print(f"DUR:{duration:.3f}", flush=True)

# ── Shared state ──
lock  = threading.Lock()
quit_flag = [False]
state = {
    "playing":           False,
    "play_start_wall":   0.0,
    "play_start_sample": 0,
    "current_sample":    0,
}


def _do_play():
    sd.stop()
    sample = state["current_sample"]
    if sample >= len(audio):
        return
    sd.play(audio[sample:], samplerate=SAMPLE_RATE, blocking=False)
    state["play_start_wall"]   = time.time()
    state["play_start_sample"] = sample
    state["playing"]           = True


def _update_sample():
    elapsed = time.time() - state["play_start_wall"]
    sample  = state["play_start_sample"] + int(elapsed * SAMPLE_RATE)
    state["current_sample"] = min(sample, len(audio))


def _pos_reporter():
    while not quit_flag[0]:
        with lock:
            if state["playing"]:
                _update_sample()
                if state["current_sample"] >= len(audio):
                    state["playing"] = False
                    sd.stop()
                else:
                    print(f"POS:{state['current_sample'] / SAMPLE_RATE:.3f}", flush=True)
        time.sleep(0.1)


threading.Thread(target=_pos_reporter, daemon=True).start()

for raw_cmd in sys.stdin:
    cmd = raw_cmd.strip()
    if not cmd:
        continue

    with lock:
        if cmd == "PLAY":
            _do_play()

        elif cmd == "PAUSE":
            if state["playing"]:
                _update_sample()
            sd.stop()
            state["playing"] = False

        elif cmd == "STOP":
            sd.stop()
            state["playing"]        = False
            state["current_sample"] = 0

        elif cmd.startswith("SEEK "):
            try:
                pos_sec = max(0.0, min(float(cmd[5:]), duration))
                sd.stop()
                state["playing"] = False
                new_sample = int(pos_sec * SAMPLE_RATE)
                state["current_sample"]    = new_sample
                state["play_start_sample"] = new_sample
                state["play_start_wall"]   = time.time()
            except ValueError:
                pass

        elif cmd == "QUIT":
            quit_flag[0] = True
            break

sd.stop()
