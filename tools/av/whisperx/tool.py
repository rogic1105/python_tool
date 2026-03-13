import sys
import tkinter as tk
import argparse
from pathlib import Path

from core.isolated_tool import IsolatedTool

_TOOL_DIR = Path(__file__).parent
RUNNER = _TOOL_DIR / "runner.py"


def _has_nvidia_gpu() -> bool:
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


class WhisperXTool(IsolatedTool):
    name = "whisperx"
    display_name = "WhisperX 語音轉錄"
    category = "av"
    description = "高精度語音轉文字，word-level 對齊 + pyannote 語者分離，輸出 SRT/TXT"

    venv_name = "whisperx"
    requirements_file = "requirements.txt"
    check_imports = ["whisperx", "torch"]

    def _resolve_requirements(self) -> Path:
        if sys.platform == "win32":
            cuda_req = _TOOL_DIR / "requirements-cuda.txt"
            if cuda_req.exists() and _has_nvidia_gpu():
                return cuda_req
        return _TOOL_DIR / "requirements.txt"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="音訊/影片檔案路徑")
        parser.add_argument("--model", default="large-v2",
                            help="模型大小 (tiny/base/small/medium/large-v2/large-v3)")
        parser.add_argument("--language", default="zh",
                            help="語言代碼 (auto/zh/en/ja/ko)")
        parser.add_argument("--speakers", type=int, default=0,
                            help="說話者人數，0 表示自動偵測")
        parser.add_argument("--batch-size", type=int, default=16,
                            help="批次大小（越大越快但更耗 VRAM）")
        parser.add_argument("--hf-token", default="",
                            help="HuggingFace token（語者分離需要）")
        parser.add_argument("--output", default=None, help="輸出目錄 (預設: ./output)")

    def _runner_path(self) -> Path:
        return RUNNER

    def _runner_args(self, args) -> list:
        from tools.av.whisperx.src.config import DEFAULT_OUTPUT_DIR
        result = [
            args.input,
            "--model", args.model,
            "--language", args.language,
            "--speakers", str(args.speakers),
            "--batch-size", str(args.batch_size),
        ]
        if getattr(args, "hf_token", ""):
            result += ["--hf-token", args.hf_token]
        result += ["--output", args.output or DEFAULT_OUTPUT_DIR]
        return result

    def _build_panel(self, parent: tk.Widget) -> tk.Widget:
        from tools.av.whisperx.src.gui_panel import WhisperXPanel
        return WhisperXPanel(parent, self)
