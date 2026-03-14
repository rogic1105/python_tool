"""
Extraction runner — runs in isolated venv via IsolatedTool.

Usage:
    python runner.py <input> <start_sec> <duration_sec> <output> <ffmpeg_path>

Stdout protocol:
    LOG:<msg>
    DONE:<output_path>
    ERROR:<msg>
"""
import os
import subprocess
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

input_file  = sys.argv[1]
start       = float(sys.argv[2])
duration    = float(sys.argv[3])
output_file = sys.argv[4]
ffmpeg      = sys.argv[5] if len(sys.argv) > 5 else "ffmpeg"


def fmt(sec):
    m = int(sec // 60)
    s = sec % 60
    return f"{m:02d}:{s:06.3f}"


print(f"LOG:擷取中：{fmt(start)} → {fmt(start + duration)}", flush=True)

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

result = subprocess.run(
    [ffmpeg, "-y", "-ss", str(start), "-i", input_file,
     "-t", str(duration), "-c", "copy", output_file],
    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
)

if result.returncode == 0:
    print(f"DONE:{output_file}", flush=True)
else:
    print(f"ERROR:{result.stderr[-600:]}", flush=True)
