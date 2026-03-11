#!/usr/bin/env python3
"""Standalone crystal path runner — no framework imports.

Output protocol:
  LOG:<message>
  DONE:<output_path>
  ERROR:<message>
"""

import sys
import os
import argparse

# Force UTF-8 stdout/stderr on Windows. Use reconfigure() to avoid GC closing the buffer.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["animation.ffmpeg_path"] = args.ffmpeg

    from core import generate_crystal_path_animation

    def log_cb(msg):
        print(f"LOG:{msg}", flush=True)

    try:
        out = generate_crystal_path_animation(args.output, log_cb=log_cb)
        print(f"DONE:{out}", flush=True)
    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
