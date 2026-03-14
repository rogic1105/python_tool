"""
Persistent playback subprocess — runs in isolated venv (pygame required).

Usage:
    python player.py <audio_file> <ffprobe_path>

Stdin commands (newline-terminated):
    PLAY
    PAUSE
    STOP
    SEEK <seconds>
    QUIT

Stdout protocol:
    DUR:<seconds>       — sent once after successful load
    POS:<seconds>       — sent every ~100ms while playing
    ERROR:<msg>         — fatal error
"""
import json
import os
import subprocess
import sys
import threading
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

import pygame

file_path = sys.argv[1]
ffprobe = sys.argv[2] if len(sys.argv) > 2 else "ffprobe"

# ── Get duration ──
try:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", file_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    duration = float(json.loads(r.stdout)["format"]["duration"])
except Exception as e:
    print(f"ERROR:無法取得音檔時長：{e}", flush=True)
    sys.exit(1)

# ── Init pygame ──
try:
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
except Exception as e:
    print(f"ERROR:pygame 初始化失敗：{e}", flush=True)
    sys.exit(1)

print(f"DUR:{duration:.3f}", flush=True)

# ── Shared state ──
lock = threading.Lock()
is_playing = False
current_pos = 0.0
play_start_wall = 0.0
play_offset = 0.0
quit_flag = [False]


def _pos_reporter():
    while not quit_flag[0]:
        with lock:
            if is_playing:
                elapsed = time.time() - play_start_wall
                pos = min(play_offset + elapsed, duration)
                print(f"POS:{pos:.3f}", flush=True)
        time.sleep(0.1)


threading.Thread(target=_pos_reporter, daemon=True).start()

# ── Command loop ──
for raw in sys.stdin:
    cmd = raw.strip()
    if not cmd:
        continue
    with lock:
        if cmd == "PLAY":
            try:
                pygame.mixer.music.play(start=current_pos)
            except Exception:
                pygame.mixer.music.play()
            play_start_wall = time.time()
            play_offset = current_pos
            is_playing = True

        elif cmd == "PAUSE":
            pygame.mixer.music.pause()
            current_pos = min(play_offset + (time.time() - play_start_wall), duration)
            is_playing = False

        elif cmd == "STOP":
            pygame.mixer.music.stop()
            current_pos = 0.0
            is_playing = False

        elif cmd.startswith("SEEK "):
            try:
                new_pos = max(0.0, min(float(cmd[5:]), duration))
            except ValueError:
                continue
            current_pos = new_pos
            if is_playing:
                try:
                    pygame.mixer.music.play(start=new_pos)
                except Exception:
                    pygame.mixer.music.play()
                play_start_wall = time.time()
                play_offset = new_pos

        elif cmd == "QUIT":
            quit_flag[0] = True
            break

try:
    pygame.mixer.music.stop()
    pygame.mixer.quit()
except Exception:
    pass
