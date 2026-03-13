import os
import math
import subprocess
import shutil
from dataclasses import dataclass

from .config import SYSTEM


@dataclass
class LabeledSegment:
    start: float
    end: float
    text: str
    speaker: str


def find_ffmpeg_executable() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    if SYSTEM == "Windows":
        user_profile = os.environ.get("USERPROFILE", "")
        program_data = os.environ.get("ProgramData", "")
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]
        if user_profile:
            common_paths.append(os.path.join(user_profile, "scoop", "shims", "ffmpeg.exe"))
        if program_data:
            common_paths.append(os.path.join(program_data, "chocolatey", "bin", "ffmpeg.exe"))
        for p in common_paths:
            if os.path.exists(p):
                return p
    return "ffmpeg"


FFMPEG_CMD = find_ffmpeg_executable()


def srt_timestamp(t: float) -> str:
    if t < 0:
        t = 0.0
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = int(t % 60)
    milliseconds = int(round((t - math.floor(t)) * 1000))
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def ensure_wav_mono16k(input_path: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_path))[0]
    out_wav = os.path.join(output_dir, f"{base}.wav")

    startupinfo = None
    if SYSTEM == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    cmd = [FFMPEG_CMD, "-y", "-i", input_path, "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", out_wav]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
    except FileNotFoundError:
        raise RuntimeError(f"找不到 FFmpeg！偵測路徑：{FFMPEG_CMD}\n請確認安裝正確。")
    except subprocess.CalledProcessError:
        raise RuntimeError("FFmpeg 轉檔失敗，請確認輸入檔案是否損壞。")
    return out_wav


def normalize_speaker(raw: str, speaker_map: dict) -> str:
    """Map SPEAKER_00, SPEAKER_01 … to S1, S2 … in encounter order."""
    if raw not in speaker_map:
        speaker_map[raw] = f"S{len(speaker_map) + 1}"
    return speaker_map[raw]
