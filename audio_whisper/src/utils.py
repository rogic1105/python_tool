import os
import math
import subprocess
import platform
import shutil  # 新增：用來尋找執行檔路徑
import numpy as np
import soundfile as sf
from dataclasses import dataclass
from typing import List, Tuple

from src.config import SYSTEM, HOP_SEC

# ==========================================
# 資料結構定義
# ==========================================
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

# ==========================================
# FFmpeg 路徑偵測 (解決 PATH 被汙染的問題)
# ==========================================
def find_ffmpeg_executable():
    """
    嘗試尋找 ffmpeg 的絕對路徑。
    優先順序：
    1. 系統 PATH 中的 ffmpeg
    2. 常見的手動安裝路徑 (Windows)
    3. 回傳 'ffmpeg' 字串讓 subprocess 自己再試一次
    """
    # 1. 使用 shutil.which 搜尋系統 PATH
    # 這會在模組載入時執行，通常這時候 PATH 還沒被汙染
    path = shutil.which("ffmpeg")
    if path:
        return path
            
    return "ffmpeg"

# 在模組層級就先鎖定路徑
FFMPEG_CMD = find_ffmpeg_executable()

# ==========================================
# 工具函式
# ==========================================
def srt_timestamp(t: float) -> str:
    if t < 0: t = 0.0
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = int(t % 60)
    milliseconds = int(round((t - math.floor(t)) * 1000))
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def ensure_wav_mono16k(input_path: str, output_dir: str) -> str:
    """使用 ffmpeg 將音訊轉為 16k mono WAV"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    base = os.path.splitext(os.path.basename(input_path))[0]
    out_wav = os.path.join(output_dir, f"{base}.wav")
    
    startupinfo = None
    if SYSTEM == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
    # 修改：使用鎖定的絕對路徑 FFMPEG_CMD
    cmd = [
        FFMPEG_CMD, "-y", "-i", input_path,
        "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
        out_wav
    ]
    
    try:
        subprocess.run(
            cmd, check=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo
        )
    except FileNotFoundError:
        # 即使我們嘗試找了路徑，subprocess 還是可能因為權限或其他原因找不到
        raise RuntimeError(f"找不到 FFmpeg 執行檔！\n偵測到的路徑為: {FFMPEG_CMD}\n請確認安裝正確。")
    except subprocess.CalledProcessError:
        raise RuntimeError("FFmpeg 轉檔失敗，請確認輸入檔案是否損壞。")
    
    return out_wav

def build_chunks(win_times: List[Tuple[float, float]], labels: np.ndarray, max_sec=300) -> List[Tuple[float, float]]:
    if not win_times: return []
    
    diar_segs: List[DiarSeg] = []
    cur_st, cur_ed, cur_lb = win_times[0][0], win_times[0][1], int(labels[0])
    gap_tol = HOP_SEC + 0.05

    for (st, ed), lb in zip(win_times[1:], labels[1:]):
        lb = int(lb)
        if lb == cur_lb and (st <= cur_ed + gap_tol):
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
        length = ed - st
        if length > max_sec:
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

        if (ed - c_st) <= max_sec:
            c_ed = ed
        else:
            flush()
            c_st, c_ed = st, ed
    flush()
    return chunks

def align_segments(whisper_segs: List[WhisperSegment], win_times: List[Tuple[float, float]], labels: np.ndarray) -> List[LabeledSegment]:
    if not win_times:
        return [LabeledSegment(s.start, s.end, s.text, "Unknown") for s in whisper_segs]

    diar_simple = []
    for (st, ed), lb in zip(win_times, labels):
        diar_simple.append({'start': st, 'end': ed, 'label': lb})
    
    uniq = sorted(set(labels))
    to_name = {lab: f"S{idx+1}" for idx, lab in enumerate(uniq)}
    
    results = []
    for seg in whisper_segs:
        best_lb = None
        best_ov = 0.0
        
        for d in diar_simple:
            ov = max(0.0, min(seg.end, d['end']) - max(seg.start, d['start']))
            if ov > best_ov:
                best_ov = ov
                best_lb = d['label']
        
        if best_lb is None:
            mid = (seg.start + seg.end) / 2
            nearest = min(diar_simple, key=lambda x: abs((x['start']+x['end'])/2 - mid))
            best_lb = nearest['label']
            
        results.append(LabeledSegment(seg.start, seg.end, seg.text, to_name[best_lb]))
        
    return results