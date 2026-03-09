#!/usr/bin/env python3
"""Standalone Demucs runner — executed inside the demucs venv.

Uses demucs.separate.main() directly (no CLI subprocess).
Auto-selects CUDA / CPU via torch.

NO imports from the project framework (core/, tools/).

Output protocol:
  LOG:<message>
  PROGRESS:1,<0-100>,
  DONE:<output_dir>
  ERROR:<message>
"""

import sys
import os
import io
import re
import shutil
import argparse

DEMUCS_MODEL = "htdemucs"


class _ProgressCapture(io.TextIOBase):
    """Intercepts demucs/tqdm stderr and converts progress to PROGRESS: lines on stdout."""
    _pat = re.compile(r"(\d+)%\|")

    def write(self, text):
        for chunk in re.split(r"[\r\n]", text):
            m = self._pat.search(chunk)
            if m:
                print(f"PROGRESS:1,{m.group(1)},", flush=True)
        return len(text)

    def flush(self):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="音訊檔案路徑")
    parser.add_argument("--output", default="output", help="輸出目錄")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR:找不到檔案: {args.input}", flush=True)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    try:
        import torch
        import demucs.separate
    except ImportError as e:
        print(f"ERROR:缺少套件: {e}", flush=True)
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"LOG:使用裝置: {device}", flush=True)
    print(f"LOG:執行 Demucs ({DEMUCS_MODEL})...", flush=True)
    print("PROGRESS:1,0,", flush=True)

    demucs_args = [
        "--two-stems", "vocals",
        "-n", DEMUCS_MODEL,
        "-d", device,
        "-o", args.output,
        args.input,
    ]

    # Intercept stderr so tqdm progress lines get converted to PROGRESS: protocol
    _orig_stderr = sys.stderr
    sys.stderr = _ProgressCapture()
    try:
        demucs.separate.main(demucs_args)
    except SystemExit:
        pass  # demucs.separate.main calls sys.exit(0) on success
    except Exception as e:
        sys.stderr = _orig_stderr
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)
    finally:
        sys.stderr = _orig_stderr

    print("PROGRESS:1,100,完成", flush=True)
    print("LOG:分離完成，整理檔案中...", flush=True)

    # Move output from htdemucs/<filename>/ up to <output>/<filename>/
    filename_no_ext = os.path.splitext(os.path.basename(args.input))[0]
    deep_path = os.path.join(args.output, DEMUCS_MODEL, filename_no_ext)
    target_path = os.path.join(args.output, filename_no_ext)

    try:
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        shutil.move(deep_path, args.output)
        model_dir = os.path.join(args.output, DEMUCS_MODEL)
        if os.path.exists(model_dir) and not os.listdir(model_dir):
            os.rmdir(model_dir)
        print(f"DONE:{target_path}", flush=True)
    except Exception as e:
        print(f"LOG:檔案整理失敗: {e}", flush=True)
        print(f"DONE:{args.output}", flush=True)


if __name__ == "__main__":
    main()
