import os
os.environ["LOKY_MAX_CPU_COUNT"] = "4"
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

import math
import subprocess
import time
import warnings
from dataclasses import dataclass
from typing import List, Optional, Tuple


import numpy as np
import librosa
import soundfile as sf
from tqdm import tqdm
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from resemblyzer import VoiceEncoder
# 延後 import faster_whisper 以防初始化錯誤
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

# =============== 基本設定 ===============
CWD = os.getcwd()   # 以目前工作目錄為根
SR = 16000          # 16k
WIN_SEC = 1.5       # 視窗長度（秒）
HOP_SEC = 0.75      # 視窗位移（秒）
ENERGY_THRESH = 0.01  # 跳過極低能量視窗的門檻
FILE_DIR = "data"
# 使用 r"" 原始字串避免 Windows 路徑反斜線問題
FILE_NAME = "0108.m4a"
INPUT_FILE  = os.path.join(FILE_DIR, FILE_NAME)
SPEAKERS = 3
MODEL = "medium"
LANGUAGE = "zh"
OUTPUT_DIR = "data_out"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, FILE_NAME)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =============== 小工具 ===============
def ensure_wav_mono16k(input_path: str) -> str:
    """
    若不是 16k/mono PCM WAV，使用 ffmpeg 轉檔到 CWD 同名 .wav
    Windows 下建議隱藏 FFmpeg 輸出以免洗版
    """
    base = os.path.splitext(os.path.basename(input_path))[0]
    out_wav = os.path.join(CWD, FILE_DIR, f"{base}.wav")
    
    # 簡單檢查是否已經存在且可用，避免重複轉檔 (可選)
    # if os.path.exists(out_wav): return out_wav

    print(f"[ffmpeg] 正在轉換格式: {input_path} -> {out_wav}")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SR),
            out_wav
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # stderr=subprocess.DEVNULL 可以隱藏 ffmpeg 的大量資訊
    except subprocess.CalledProcessError:
        print("轉檔失敗，請確認已安裝 ffmpeg 並加入環境變數 Path 中。")
        raise
    return out_wav


def srt_timestamp(t: float) -> str:
    if t < 0:
        t = 0.0
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = int(t % 60)
    milliseconds = int(round((t - math.floor(t)) * 1000))
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def overlap(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    a0, a1 = a
    b0, b1 = b
    return max(0.0, min(a1, b1) - max(a0, b0))


# =============== 資料結構 ===============
@dataclass
class WhisperSegment:
    start: float
    end: float
    text: str


@dataclass
class DiarSeg:
    start: float
    end: float
    label: int


@dataclass
class LabeledSegment:
    start: float
    end: float
    text: str
    speaker: str


# =============== 語者分離（resemblyzer + KMeans） ===============
def compute_window_embeddings(
    wav: np.ndarray,
    sr: int,
    show_progress: bool = True,
    tqdm_desc: str = "計算語者向量"
) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    
    # 在 Windows 上 VoiceEncoder有時需要明確指定 device，這裡預設 cpu
    encoder = VoiceEncoder(device="cpu") 
    win_len = int(WIN_SEC * sr)
    hop_len = int(HOP_SEC * sr)

    embeddings = []
    win_times = []

    if len(wav) < win_len:
        pad = np.zeros(win_len - len(wav), dtype=wav.dtype)
        wav = np.concatenate([wav, pad], axis=0)

    total_windows = 1 + max(0, (len(wav) - win_len) // hop_len)
    iterator = range(0, len(wav) - win_len + 1, hop_len)
    
    if show_progress:
        iterator = tqdm(iterator, total=total_windows, desc=tqdm_desc, unit="窗")

    for start in iterator:
        end = start + win_len
        chunk = wav[start:end]
        rms = float(np.sqrt(np.mean(chunk**2)) + 1e-9)
        if rms < ENERGY_THRESH:
            continue
        emb = encoder.embed_utterance(chunk)
        embeddings.append(emb)
        win_times.append((start / sr, end / sr))

    if not embeddings:
        print("警告：全部片段能量過低，改為強制取樣...")
        iterator2 = range(0, len(wav) - win_len + 1, hop_len)
        for start in iterator2:
            end = start + win_len
            chunk = wav[start:end]
            emb = encoder.embed_utterance(chunk)
            embeddings.append(emb)
            win_times.append((start / sr, end / sr))

    return np.stack(embeddings, axis=0), win_times


def cluster_embeddings(
    embeddings: np.ndarray,
    num_speakers: Optional[int],
    show_progress: bool = True
) -> np.ndarray:
    
    if embeddings.shape[0] == 1:
        return np.zeros((1,), dtype=int)

    # 固定 random_state 以確保結果可重現
    kmeans_kwargs = {"n_init": 10, "random_state": 42}

    if num_speakers is None:
        k_min = 2
        k_max = min(6, embeddings.shape[0])
        best_k, best_score, best_labels = None, -1.0, None

        ks = range(k_min, k_max + 1)
        if show_progress:
            ks = tqdm(ks, desc="KMeans 自動搜尋 K", unit="k")

        for k in ks:
            km = KMeans(n_clusters=k, **kmeans_kwargs).fit(embeddings)
            try:
                score = silhouette_score(embeddings, km.labels_)
            except Exception:
                score = -1.0
            if score > best_score:
                best_k, best_score, best_labels = k, score, km.labels_
        
        if best_labels is None:
            km = KMeans(n_clusters=2, **kmeans_kwargs).fit(embeddings)
            return km.labels_
        return best_labels
    else:
        km = KMeans(n_clusters=num_speakers, **kmeans_kwargs).fit(embeddings)
        return km.labels_


def merge_contiguous_windows(win_times: List[Tuple[float, float]], labels: np.ndarray) -> List[DiarSeg]:
    if not win_times:
        return []

    diar: List[DiarSeg] = []
    cur_start, cur_end, cur_label = win_times[0][0], win_times[0][1], int(labels[0])
    gap_tol = HOP_SEC + 0.05 # 稍微寬容一點的容忍度

    for (st, ed), lb in zip(win_times[1:], labels[1:]):
        lb = int(lb)
        # 如果標籤相同 且 時間是連續的(或重疊)
        if lb == cur_label and (st <= cur_end + gap_tol):
            cur_end = max(cur_end, ed)
        else:
            diar.append(DiarSeg(cur_start, cur_end, cur_label))
            cur_start, cur_end, cur_label = st, ed, lb
    diar.append(DiarSeg(cur_start, cur_end, cur_label))
    return diar


def diarize_with_resemblyzer(
    wav_path: str,
    num_speakers: Optional[int],
    show_progress: bool = True
) -> List[DiarSeg]:
    print(f"[diar] 載入音檔: {wav_path}")
    wav, sr = librosa.load(wav_path, sr=SR, mono=True)

    embeddings, win_times = compute_window_embeddings(
        wav, sr, show_progress=show_progress
    )

    labels = cluster_embeddings(
        embeddings, num_speakers, show_progress=show_progress
    )

    diar = merge_contiguous_windows(win_times, labels)
    return diar

def _build_chunks_from_diar(
    diar: List[DiarSeg],
    max_sec: int = 300,
    group_across_speakers: bool = True
) -> List[Tuple[float, float]]:
    if not diar:
        return []

    chunks: List[Tuple[float, float]] = []
    cur_st: Optional[float] = None
    cur_ed: Optional[float] = None

    def flush_current():
        nonlocal cur_st, cur_ed
        if cur_st is not None and cur_ed is not None and cur_ed > cur_st:
            chunks.append((cur_st, cur_ed))
        cur_st, cur_ed = None, None

    for d in diar:
        seg_st, seg_ed = float(d.start), float(d.end)
        seg_len = seg_ed - seg_st

        if seg_len > max_sec:
            flush_current()
            pos = seg_st
            while pos < seg_ed:
                ed = min(pos + max_sec, seg_ed)
                chunks.append((pos, ed))
                pos = ed
            continue

        if cur_st is None:
            cur_st, cur_ed = seg_st, seg_ed
            continue

        if group_across_speakers and (seg_ed - cur_st) <= max_sec:
            cur_ed = seg_ed
        else:
            flush_current()
            cur_st, cur_ed = seg_st, seg_ed

    flush_current()
    return chunks


# =============== Whisper 轉錄 ===============
def transcribe_with_whisper(
    audio_data, # path or numpy array
    model_size: str = "medium",
    language: str = "zh",
    device: str = "cpu",          # Windows 預設建議 CPU，除非有裝 CUDA
    compute_type: str = "int8",
    beam_size: int = 1,
    condition_on_previous_text: bool = False,
):
    if WhisperModel is None:
        raise RuntimeError("未安裝 faster-whisper，請先 `pip install -U faster-whisper`")

    # print(f"[whisper] faster-whisper device={device}, compute_type={compute_type}")
    
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as e:
        print(f"\n[Error] 模型載入失敗。若使用 GPU 請確認已安裝 cuDNN 與 zlibwapi.dll。")
        print(f"錯誤訊息: {e}")
        print("嘗試切換回 CPU 模式重試...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

    segments, info = model.transcribe(
        audio_data,
        language=language,
        beam_size=beam_size,
        vad_filter=False, 
        condition_on_previous_text=condition_on_previous_text,
    )
    # 必須轉成 list 才會真正開始計算 (generator)
    return [WhisperSegment(float(s.start), float(s.end), s.text.strip()) for s in segments]


# 修改這個函式，讓它接受 model 物件，而不是自己在裡面載入
def transcribe_with_whisper_by_diar_chunks(
    wav_path: str,
    diar: List[DiarSeg],
    model: object,  # <--- 修改這裡：接收外部傳入的模型
    language: str = "zh",
    max_chunk_sec: int = 300,
    show_progress: bool = True,
) -> List[WhisperSegment]:
    
    chunks = _build_chunks_from_diar(diar, max_sec=max_chunk_sec, group_across_speakers=True)
    if not chunks:
        return []

    # 讀取音檔
    wav, sr = librosa.load(wav_path, sr=SR, mono=True)
    all_segs: List[WhisperSegment] = []

    # --- 移除原本這裡的 model = WhisperModel(...) ---

    iterator = chunks if not show_progress else tqdm(chunks, desc="Whisper 轉錄", unit="段")
    
    for (st, ed) in iterator:
        s_idx = max(0, int(st * sr))
        e_idx = min(len(wav), int(ed * sr))
        
        chunk_wav = wav[s_idx:e_idx].astype(np.float32, copy=False)
        
        # 直接使用傳入的 model
        segments, info = model.transcribe(
            chunk_wav,
            language=language,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False
        )
        
        for s in segments:
            all_segs.append(WhisperSegment(s.start + st, s.end + st, s.text.strip()))
            
    return all_segs

# =============== 對齊 & 輸出 ===============
def align_whisper_to_speakers(
    whisper_segs: List[WhisperSegment],
    diar: List[DiarSeg],
    show_progress: bool = True,
) -> List[LabeledSegment]:
    if not diar:
        return [LabeledSegment(s.start, s.end, s.text, "Unknown") for s in whisper_segs]

    labeled: List[LabeledSegment] = []
    # 說話者標籤映射 S1, S2, ...
    uniq = sorted(set(d.label for d in diar))
    to_name = {lab: f"S{idx+1}" for idx, lab in enumerate(uniq)}

    iterator = tqdm(whisper_segs, desc="對齊語者", unit="段") if show_progress else whisper_segs

    for seg in iterator:
        best_lb, best_ov = None, 0.0
        for d in diar:
            ov = overlap((seg.start, seg.end), (d.start, d.end))
            if ov > best_ov:
                best_ov = ov
                best_lb = d.label

        if best_lb is None or best_ov == 0.0:
            # 沒重疊則找最近的
            mid = 0.5 * (seg.start + seg.end)
            nearest = min(diar, key=lambda x: abs((x.start + x.end) * 0.5 - mid))
            best_lb = nearest.label

        labeled.append(LabeledSegment(seg.start, seg.end, seg.text, to_name[best_lb]))
    return labeled


def write_srt(labeled: List[LabeledSegment], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(labeled, 1):
            f.write(f"{i}\n")
            f.write(f"{srt_timestamp(seg.start)} --> {srt_timestamp(seg.end)}\n")
            f.write(f"{seg.speaker}: {seg.text}\n\n")


def write_txt(labeled: List[LabeledSegment], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for seg in labeled:
            f.write(f"[{srt_timestamp(seg.start)} {seg.speaker}] {seg.text}\n")


# =============== 主程式 ===============
def transcribe_with_diarization(
    input_audio: str,
    model_size: str = "medium",
    language: str = "zh",
    num_speakers: Optional[int] = None,
    device: str = "cuda",
    compute_type: str = "float16"
):
    if not os.path.isabs(input_audio):
        input_audio = os.path.join(CWD, input_audio)
    
    if not os.path.exists(input_audio):
        print(f"錯誤: 找不到檔案 {input_audio}")
        return

    # 1. 轉檔
    wav_path = ensure_wav_mono16k(input_audio)

    # 2. 語者分離
    diar = diarize_with_resemblyzer(wav_path, num_speakers=num_speakers, show_progress=True)

    # --- 修改重點：在這裡載入模型，確保它在存檔前不會被關閉 ---
    print(f"[whisper] 載入模型: {model_size} ({device}, {compute_type})...")
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as e:
        print(f"[Error] GPU 初始化失敗: {e}")
        return

    # 3. 轉錄 (傳入 model)
    t_start = time.time()
    wsegs = transcribe_with_whisper_by_diar_chunks(
        wav_path=wav_path,
        diar=diar,
        model=model,  # <--- 傳入模型
        language=language,
        show_progress=True,
    )
    print(f"Whisper 轉錄耗時: {time.time() - t_start:.2f} 秒")
    
    # 4. 對齊與輸出
    labeled = align_whisper_to_speakers(wsegs, diar, show_progress=True)

    file_name = os.path.splitext(os.path.basename(wav_path))[0]
    srt_path = os.path.join(OUTPUT_DIR, f"{file_name}.srt")
    txt_path = os.path.join(OUTPUT_DIR, f"{file_name}.txt")
    write_srt(labeled, srt_path)
    write_txt(labeled, txt_path)

    print(f"\n[完成] 輸出檔案：\n1. {srt_path}\n2. {txt_path}")
    
    # 5. 手動釋放模型 (如果這裡崩潰也沒關係，因為檔案已經存好了)
    del model
    return labeled


if __name__ == "__main__":
    # 在 Windows 上，建議先用 CPU 跑，除非你有安裝 CUDA 11.x/12.x 及 cuDNN 
    # 如果你有 NVIDIA 顯卡且配置好環境，可改回 "cuda"
    WHISPER_DEVICE = "cuda"  
    
    # 如果用 cpu，建議用 int8；如果用 cuda，可用 float16
    COMPUTE_TYPE = "float16"   

    transcribe_with_diarization(
        input_audio=INPUT_FILE,
        model_size=MODEL,
        language=LANGUAGE,
        num_speakers=SPEAKERS,
        device=WHISPER_DEVICE,
        compute_type=COMPUTE_TYPE
    )