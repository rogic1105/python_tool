import tkinter as tk
import argparse
from pathlib import Path

from core.isolated_tool import IsolatedTool

RUNNER = Path(__file__).parent / "runner.py"


class WhisperTool(IsolatedTool):
    name = "whisper"
    display_name = "Whisper 語音轉錄"
    category = "av"
    description = "本機端語音轉文字，支援多語言與語者分離，輸出 SRT/TXT"

    venv_name = "whisper"
    requirements_file = "requirements.txt"
    check_imports = ["faster_whisper", "resemblyzer", "librosa", "sklearn"]

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="音訊/影片檔案路徑")
        parser.add_argument("--model", default="medium",
                            help="模型大小 (tiny/base/small/medium/large-v3)")
        parser.add_argument("--language", default="zh", help="語言代碼 (zh/en/ja/ko)")
        parser.add_argument("--speakers", type=int, default=0,
                            help="說話者人數，0 表示自動偵測")
        parser.add_argument("--output", default=None, help="輸出目錄 (預設: ./output)")

    def _runner_path(self) -> Path:
        return RUNNER

    def _runner_args(self, args) -> list:
        from tools.av.whisper.src.config import DEFAULT_OUTPUT_DIR
        result = [args.input, "--model", args.model, "--language", args.language,
                  "--speakers", str(args.speakers)]
        result += ["--output", args.output or DEFAULT_OUTPUT_DIR]
        return result

    def _build_panel(self, parent: tk.Widget) -> tk.Widget:
        """Called by IsolatedPanel after venv is confirmed ready."""
        from tools.av.whisper.src.gui_panel import WhisperPanel
        return WhisperPanel(parent, self)
