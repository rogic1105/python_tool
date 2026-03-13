import os
import math
import subprocess
import platform
import shutil
import numpy as np
import soundfile as sf
from dataclasses import dataclass
from typing import List, Tuple

from .config import SYSTEM, HOP_SEC


@dataclass
class DiarSeg:
    start: float
    end: float
    label: int


@dataclass
class WhisperSegment:
    start: float
    end: float
    text: str


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


def build_chunks(win_times: List[Tuple[float, float]], labels, max_sec: int = 300) -> List[Tuple[float, float]]:
    if not win_times:
        return []

    diar_segs: List[DiarSeg] = []
    cur_st, cur_ed, cur_lb = win_times[0][0], win_times[0][1], int(labels[0])
    gap_tol = HOP_SEC + 0.05

    for (st, ed), lb in zip(win_times[1:], labels[1:]):
        lb = int(lb)
        if lb == cur_lb and st <= cur_ed + gap_tol:
            cur_ed = max(cur_ed, ed)
        else:
            diar_segs.append(DiarSeg(cur_st, cur_ed, cur_lb))
            cur_st, cur_ed, cur_lb = st, ed, lb
    diar_segs.append(DiarSeg(cur_st, cur_ed, cur_lb))

    chunks = []
    c_st, c_ed = None, None

    def flush():
        nonlocal c_st, c_ed
        if c_st is not None and c_ed is not None and c_ed > c_st:
            chunks.append((c_st, c_ed))
        c_st, c_ed = None, None

    for seg in diar_segs:
        st, ed = seg.start, seg.end
        if ed - st > max_sec:
            flush()
            pos = st
            while pos < ed:
                nxt = min(pos + max_sec, ed)
                chunks.append((pos, nxt))
                pos = nxt
            continue
        if c_st is None:
            c_st, c_ed = st, ed
            continue
        if ed - c_st <= max_sec:
            c_ed = ed
        else:
            flush()
            c_st, c_ed = st, ed
    flush()
    return chunks


def _build_align_context(win_times, labels):
    """Pre-compute shared data for alignment (used by both align variants)."""
    diar_simple = [{"start": st, "end": ed, "label": lb}
                   for (st, ed), lb in zip(win_times, labels)]
    uniq = sorted(set(labels))
    to_name = {lab: f"S{idx+1}" for idx, lab in enumerate(uniq)}
    return diar_simple, to_name


def _best_speaker(seg: WhisperSegment, diar_simple: list, to_name: dict) -> str:
    best_lb, best_ov = None, 0.0
    for d in diar_simple:
        ov = max(0.0, min(seg.end, d["end"]) - max(seg.start, d["start"]))
        if ov > best_ov:
            best_ov, best_lb = ov, d["label"]
    if best_lb is None:
        mid = (seg.start + seg.end) / 2
        nearest = min(diar_simple, key=lambda x: abs((x["start"] + x["end"]) / 2 - mid))
        best_lb = nearest["label"]
    return to_name[best_lb]


def align_segments(
    whisper_segs: List[WhisperSegment],
    win_times: List[Tuple[float, float]],
    labels,
) -> List[LabeledSegment]:
    if not win_times:
        return [LabeledSegment(s.start, s.end, s.text, "Unknown") for s in whisper_segs]
    diar_simple, to_name = _build_align_context(win_times, labels)
    return [LabeledSegment(s.start, s.end, s.text, _best_speaker(s, diar_simple, to_name))
            for s in whisper_segs]


def align_segments_stream(
    whisper_segs: List[WhisperSegment],
    win_times: List[Tuple[float, float]],
    labels,
):
    """Generator version: yields one LabeledSegment at a time for streaming writes."""
    if not win_times:
        for s in whisper_segs:
            yield LabeledSegment(s.start, s.end, s.text, "Unknown")
        return
    diar_simple, to_name = _build_align_context(win_times, labels)
    for s in whisper_segs:
        yield LabeledSegment(s.start, s.end, s.text, _best_speaker(s, diar_simple, to_name))
