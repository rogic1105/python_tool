#!/usr/bin/env python3
"""Standalone WhisperX runner — executed inside the whisperx venv.

This file has NO imports from the project framework (core/, tools/).
It only uses its own src/ directory and third-party packages.

Output protocol (one prefix per line, parsed by gui_panel.py):
  LOG:<message>
  PROGRESS:<stage>,<0-100>,<optional msg>
  TEXT:<transcript line>
  CLEAR_CONTENT:
  DONE:<srt_path>
  ERROR:<message>
"""

import sys
import os
import argparse

# Force UTF-8 stdout/stderr on Windows.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Make src/ importable relative to this file's directory
sys.path.insert(0, os.path.dirname(__file__))

from src.config import setup_env, DEFAULT_OUTPUT_DIR
from src.logic import Pipeline


def log_cb(msg: str):
    print(f"LOG:{msg}", flush=True)


def progress_cb(stage: int, val: float, msg: str = None):
    print(f"PROGRESS:{stage},{val},{msg or ''}", flush=True)


def transcript_cb(text):
    if text is None:
        print("CLEAR_CONTENT:", flush=True)
    else:
        print(f"TEXT:{text}", flush=True)


def main():
    setup_env()

    parser = argparse.ArgumentParser(description="WhisperX Diarization Runner")
    parser.add_argument("input", help="音訊/影片路徑")
    parser.add_argument("--model", default="large-v2")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--speakers", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--hf-token", default="")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    pipeline = Pipeline(args.output)
    try:
        srt_path, _ = pipeline.run(
            args.input,
            args.model,
            args.language,
            args.speakers,
            args.hf_token,
            args.batch_size,
            log_cb=log_cb,
            progress_cb=progress_cb,
            transcript_cb=transcript_cb,
        )
        print(f"DONE:{srt_path}", flush=True)
    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
