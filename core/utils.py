import json
import os
import shutil
import platform
import subprocess
import sys
from pathlib import Path

_PREFS_FILE = Path(__file__).parent.parent / ".venvs" / "ui_prefs.json"


def load_pref(key: str, default=None):
    """Load a persisted UI preference value."""
    try:
        data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        return data.get(key, default)
    except Exception:
        return default


def save_pref(key: str, value) -> None:
    """Persist a UI preference value."""
    _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_PREFS_FILE.read_text(encoding="utf-8")) if _PREFS_FILE.exists() else {}
    except Exception:
        data = {}
    data[key] = value
    _PREFS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

SYSTEM = platform.system()


def find_ffmpeg() -> str:
    """Find ffmpeg executable path, checking common install locations."""
    path = shutil.which("ffmpeg")
    if path:
        return path

    if SYSTEM == "Windows":
        user_profile = os.environ.get("USERPROFILE", "")
        program_data = os.environ.get("ProgramData", "")
        local_app_data = os.environ.get("LOCALAPPDATA", "")

        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            r"C:\CmdTools\ffmpeg\bin\ffmpeg.exe",
        ]
        if user_profile:
            common_paths += [
                os.path.join(user_profile, "scoop", "shims", "ffmpeg.exe"),
                os.path.join(user_profile, "scoop", "apps", "ffmpeg", "current", "bin", "ffmpeg.exe"),
            ]
        if program_data:
            common_paths.append(os.path.join(program_data, "chocolatey", "bin", "ffmpeg.exe"))
        if local_app_data:
            common_paths.append(os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "ffmpeg.exe"))

        for p in common_paths:
            if os.path.exists(p):
                return p

    return "ffmpeg"


FFMPEG_CMD = find_ffmpeg()


def check_ffmpeg() -> None:
    """Exit with a helpful message if ffmpeg is not found."""
    if not shutil.which(FFMPEG_CMD) and not os.path.exists(FFMPEG_CMD):
        sys.exit(
            "[錯誤] 找不到 FFmpeg！請安裝後將其加入 PATH：\n"
            "  Mac:     brew install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html\n"
            "  Linux:   sudo apt install ffmpeg\n"
        )


def open_folder(path: str) -> None:
    """Open a folder in the OS file manager (cross-platform).
    If path is a file, opens its parent directory.
    Does nothing if the path is empty or does not exist.
    """
    p = Path(str(path).strip())
    if not path or not p.exists():
        return
    if p.is_file():
        p = p.parent
    if SYSTEM == "Windows":
        os.startfile(str(p))
    elif SYSTEM == "Darwin":
        subprocess.run(["open", str(p)])
    else:
        subprocess.run(["xdg-open", str(p)])


def get_best_h264_codec() -> tuple:
    """Return (codec, extra_args_list) based on available hardware."""
    if SYSTEM == "Darwin":
        return "h264_videotoolbox", ["-q:v", "65"]
    try:
        result = subprocess.run(
            [FFMPEG_CMD, "-encoders"], capture_output=True, text=True, timeout=5
        )
        if "h264_nvenc" in result.stdout:
            return "h264_nvenc", []
    except Exception:
        pass
    return "libx264", ["-preset", "slow", "-crf", "18"]
