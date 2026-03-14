"""
Video clip extraction runner.

Usage:
    python runner.py <input> <start_sec> <duration_sec> <output> <ffmpeg> [--reencode]

Stdout protocol:
    LOG:<msg>
    DONE:<output_path>
    ERROR:<msg>
"""
import os
import subprocess
import sys


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 6:
        print("ERROR:參數不足", flush=True)
        sys.exit(1)

    input_file  = sys.argv[1]
    start       = float(sys.argv[2])
    duration    = float(sys.argv[3])
    output_file = sys.argv[4]
    ffmpeg      = sys.argv[5]
    reencode    = "--reencode" in sys.argv

    def fmt(sec):
        m = int(sec // 60)
        s = sec % 60
        return f"{m:02d}:{s:06.3f}"

    print(f"LOG:擷取中：{fmt(start)} → {fmt(start + duration)}", flush=True)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    if reencode:
        cmd = [ffmpeg, "-y", "-i", input_file,
               "-ss", str(start), "-t", str(duration),
               "-c:v", "libx264", "-c:a", "aac", output_file]
    else:
        cmd = [ffmpeg, "-y",
               "-ss", str(start), "-i", input_file,
               "-t", str(duration), "-c", "copy", output_file]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )

    if result.returncode == 0:
        print(f"DONE:{output_file}", flush=True)
    else:
        print(f"ERROR:{result.stderr[-600:]}", flush=True)


if __name__ == "__main__":
    main()
