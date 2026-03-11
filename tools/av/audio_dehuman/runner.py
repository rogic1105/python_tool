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

# Force UTF-8 stdout/stderr on Windows. Use reconfigure() to avoid GC closing the buffer.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEMUCS_MODEL = "htdemucs"


def _patch_torchaudio_if_needed(torchaudio_mod) -> bool:
    """
    torchaudio 2.5+ switched its default save backend to torchcodec.
    When torchcodec is absent, every torchaudio.save() raises:
      "TorchCodec is required for save_with_torchcodec."

    This function detects the problem with a cheap dummy save and, if
    triggered, replaces torchaudio.save with a soundfile-based version
    that writes WAV files without torchcodec.

    Returns True if the patch was applied, False if no patch was needed.
    """
    import torch as _torch

    # Quick probe: try saving 0.1 s of silence into a BytesIO
    _buf = io.BytesIO()
    try:
        torchaudio_mod.save(_buf, _torch.zeros(1, 1600), 16000, format="wav")
        return False  # works fine — no patch needed
    except Exception as _e:
        if "torchcodec" not in str(_e).lower():
            return False  # different error, don't interfere

    # torchcodec required but missing → apply soundfile fallback
    try:
        import soundfile as _sf
        import numpy as _np
    except ImportError:
        # soundfile not installed; warn but don't abort yet — the caller
        # will catch the torchcodec error and print a clearer message.
        return False

    def _sf_save(uri, src, sample_rate, *, bits_per_sample=16, **_kwargs):
        subtype = "PCM_24" if bits_per_sample == 24 else "PCM_16"
        data = src.cpu().numpy()          # shape: (channels, samples)
        if data.ndim == 2:
            data = data.T                 # soundfile wants (samples, channels)
        _sf.write(str(uri), data, sample_rate, subtype=subtype)

    torchaudio_mod.save = _sf_save
    print("LOG:torchaudio 儲存後端: soundfile (torchcodec 未安裝，自動切換)", flush=True)
    return True


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
        import torchaudio
        import demucs.separate
    except ImportError as e:
        print(f"ERROR:缺少套件: {e}", flush=True)
        sys.exit(1)

    # ── torchaudio save-backend patch ────────────────────────────────────────
    # torchaudio 2.5+ switched its default save backend to torchcodec.
    # When torchcodec is not installed every torchaudio.save() call fails.
    # We detect this at startup and replace torchaudio.save with a
    # soundfile-based implementation that handles WAV output directly.
    _patch_applied = _patch_torchaudio_if_needed(torchaudio)
    # ─────────────────────────────────────────────────────────────────────────

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
        err = str(e)
        if "torchcodec" in err.lower():
            print("ERROR:torchaudio 儲存後端需要 torchcodec，且 soundfile fallback 也不可用。"
                  "請在環境中執行: pip install soundfile", flush=True)
        else:
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
