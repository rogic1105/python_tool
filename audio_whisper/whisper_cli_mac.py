import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0") 
import math
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

import time
from tqdm import tqdm
import numpy as np
import librosa
import soundfile as sf
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import whisper
from resemblyzer import VoiceEncoder
from faster_whisper import WhisperModel

# =============== 基本設定 ===============
CWD = os.getcwd()   # 以目前工作目錄為根
SR = 16000          # 16k
WIN_SEC = 1.5       # 視窗長度（秒）
HOP_SEC = 0.75      # 視窗位移（秒）
ENERGY_THRESH = 0.01  # 跳過極低能量視窗的門檻（0~1，依音源可微調）
FILE_DIR = "data"
FILE_NAME = "0108.m4a"
INPUT_FILE  = os.path.join(FILE_DIR, FILE_NAME)
SPEAKERS = 3
MODEL = "medium"
LANGUAGE = "zh"
OUTPUT_DIR = "data_out"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, FILE_NAME)

os.makedirs(OUTPUT_DIR, exist_ok=True)
# MODEL = "medium.en"
# LANGUAGE = "en"
        
# tiny.en, tiny, base.en, base, small.en, small, medium.en, medium, large-v1, large-v2, large-v3, large, distil-large-v2, distil-medium.en, distil-small.en, distil-large-v3, distil-large-v3.5, large-v3-turbo, turbo

# =============== 小工具 ===============
def ensure_wav_mono16k(input_path: str) -> str:
    """
    若不是 16k/mono PCM WAV，使用 ffmpeg 轉檔到 CWD 同名 .wav
    """
    base = os.path.splitext(os.path.basename(input_path))[0]
    out_wav = os.path.join(CWD, FILE_DIR, f"{base}.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SR),
        out_wav
    ], check=True)
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


def _detect_whisper_device() -> Tuple[str, bool]:
    """
    回傳(device, use_fp16)。CUDA 用 fp16，其它(包含 MPS/CPU) 用 fp32。
    """
    import torch
    if torch.backends.mps.is_available():
        return "mps", False
    if torch.cuda.is_available():
        return "cuda", True
    return "cpu", False


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
    label: int  # 聚類後的整數標籤


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
    tqdm_desc: str = "計算語者向量（過濾低能量）"
) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    """
    以固定長度滑動視窗計算 resemblyzer 語者向量。
    回傳：
      - embeddings: (N, D) 矩陣
      - win_times: 每個視窗的 (start_sec, end_sec)
    """
    encoder = VoiceEncoder()
    win_len = int(WIN_SEC * sr)
    hop_len = int(HOP_SEC * sr)

    embeddings = []
    win_times = []

    # 若音檔過短，補零到至少一個視窗
    if len(wav) < win_len:
        pad = np.zeros(win_len - len(wav), dtype=wav.dtype)
        wav = np.concatenate([wav, pad], axis=0)

    total_windows = 1 + max(0, (len(wav) - win_len) // hop_len)

    iterator = range(0, len(wav) - win_len + 1, hop_len)
    if show_progress:
        iterator = tqdm(iterator, total=total_windows, desc=tqdm_desc, unit="窗")

    # 第一輪：過濾過低能量的窗口
    for start in iterator:
        end = start + win_len
        chunk = wav[start:end]
        rms = float(np.sqrt(np.mean(chunk**2)) + 1e-9)
        if rms < ENERGY_THRESH:
            continue
        emb = encoder.embed_utterance(chunk)
        embeddings.append(emb)
        win_times.append((start / sr, end / sr))

    # 若全部被過濾 → 強制取樣全部視窗再跑一次
    if not embeddings:
        iterator2 = range(0, len(wav) - win_len + 1, hop_len)
        if show_progress:
            iterator2 = tqdm(iterator2, total=total_windows, desc="無通過，改為強制取樣", unit="窗")
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
    show_progress: bool = True,
    tqdm_desc: str = "KMeans 試 K"
) -> np.ndarray:
    """
    對語者向量做 KMeans。若 num_speakers 為 None，嘗試 2..6，取 silhouette 分數最佳者。
    回傳每個向量的 cluster 標籤（0..k-1）。
    """
    if embeddings.shape[0] == 1:
        return np.zeros((1,), dtype=int)

    if num_speakers is None:
        k_min = 2
        k_max = min(6, embeddings.shape[0])
        best_k, best_score, best_labels = None, -1.0, None

        ks = range(k_min, k_max + 1)
        ks_iter = tqdm(ks, desc=tqdm_desc, unit="k") if show_progress else ks

        for k in ks_iter:
            km = KMeans(n_clusters=k, random_state=0, n_init="auto").fit(embeddings)
            labels = km.labels_
            try:
                score = silhouette_score(embeddings, labels)
            except Exception:
                score = -1.0
            if score > best_score:
                best_k, best_score, best_labels = k, score, labels
        if best_labels is None:
            km = KMeans(n_clusters=2, random_state=0, n_init="auto").fit(embeddings)
            return km.labels_
        return best_labels
    else:
        km = KMeans(n_clusters=num_speakers, random_state=0, n_init="auto").fit(embeddings)
        return km.labels_


def merge_contiguous_windows(win_times: List[Tuple[float, float]], labels: np.ndarray) -> List[DiarSeg]:
    """
    將相鄰且標籤相同的視窗合併成較長的語者片段。
    """
    if not win_times:
        return []

    diar: List[DiarSeg] = []
    cur_start, cur_end, cur_label = win_times[0][0], win_times[0][1], int(labels[0])
    gap_tol = HOP_SEC + 1e-6

    for (st, ed), lb in zip(win_times[1:], labels[1:]):
        lb = int(lb)
        if lb == cur_label and (st - cur_end) <= gap_tol:
            cur_end = ed
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
    """
    讀取 wav、計算語者向量（含進度）、KMeans 聚類（含進度）、合併視窗。
    """
    # 載入音檔（顯示進度）
    print("[diar] 載入音檔…")
    wav, sr = librosa.load(wav_path, sr=SR, mono=True)

    # 視窗嵌入（進度）
    embeddings, win_times = compute_window_embeddings(
        wav, sr, show_progress=show_progress, tqdm_desc="計算語者向量（過濾低能量）"
    )

    # 聚類（進度）
    labels = cluster_embeddings(
        embeddings, num_speakers,
        show_progress=show_progress, tqdm_desc="KMeans 嘗試最佳 K"
    )

    # 合併（資料量小，略過進度條）
    diar = merge_contiguous_windows(win_times, labels)
    return diar

def _build_chunks_from_diar(
    diar: List[DiarSeg],
    max_sec: int = 300,
    group_across_speakers: bool = True
) -> List[Tuple[float, float]]:
    """
    回傳 [(chunk_start_sec, chunk_end_sec), ...]，切點皆落在語者邊界上。
    單一語者片段若 > max_sec，會在該片段內細切，但不影響後續片段。
    """
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

        # 單片段本身就超過 max_sec -> 在片段內細切
        if seg_len > max_sec:
            flush_current()
            pos = seg_st
            while pos < seg_ed:
                ed = min(pos + max_sec, seg_ed)
                chunks.append((pos, ed))
                pos = ed
            continue

        # 正常情況：嘗試併入目前 chunk，或開新 chunk
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
    wav_path: str,
    model_size: str = "medium",
    language: str = "zh",
    backend: str = "faster",            # "faster" | "torch" | "cpp"（預留）
    compute_type: str = "int8",         # faster-whisper: "int8"/"int8_float16"/"float16"/"float32"
    beam_size: int = 1,
    condition_on_previous_text: bool = False,
):
    """
    轉錄後端可切換：
      - faster: 使用 faster-whisper（建議，Apple Silicon/CPU 都快）
      - torch:  使用 openai/whisper + PyTorch（維持你原來邏輯，會自動從 MPS 退回 CPU）
      - cpp:    （預留）若你想之後接 whisper.cpp 的 CLI
    回傳 List[WhisperSegment]
    """
    backend = backend.lower()

    if backend == "faster":
        if WhisperModel is None:
            raise RuntimeError("未安裝 faster-whisper，請先 `pip install -U faster-whisper`")
        # device="auto" 會自行選 GPU/CPU；在 Mac 上即使走 CPU 也常比 torch 版快
        print(f"[whisper] faster-whisper device=auto, compute_type={compute_type}")
        model = WhisperModel(model_size, device="auto", compute_type=compute_type)
        segments, info = model.transcribe(
            wav_path,
            language=language,
            beam_size=beam_size,
            vad_filter=False,  # 若你外部先做 VAD/能量過濾，這裡就保持 False
            condition_on_previous_text=condition_on_previous_text,
        )
        return [WhisperSegment(float(s.start), float(s.end), s.text.strip()) for s in segments]

    elif backend == "torch":
        # 保留你原本的 MPS→CUDA→CPU 偵測與 SparseMPS 回退
        import torch, whisper as _whisper
        if torch.backends.mps.is_available():
            device, use_fp16 = "mps", False
        elif torch.cuda.is_available():
            device, use_fp16 = "cuda", True
        else:
            device, use_fp16 = "cpu", False
        print(f"[whisper] 嘗試 device={device}, fp16={use_fp16}")
        try:
            model = _whisper.load_model(model_size, device=device)
            result = model.transcribe(
                wav_path, language=language, fp16=use_fp16,
                beam_size=beam_size, condition_on_previous_text=condition_on_previous_text
            )
        except (NotImplementedError, RuntimeError) as e:
            msg = str(e)
            if "SparseMPS" in msg or "aten::_sparse_coo_tensor_with_dims_and_tensors" in msg:
                print("[whisper] MPS 缺算子（稀疏張量），自動改用 CPU。")
                device, use_fp16 = "cpu", False
                model = _whisper.load_model(model_size, device=device)
                result = model.transcribe(
                    wav_path, language=language, fp16=use_fp16,
                    beam_size=beam_size, condition_on_previous_text=condition_on_previous_text
                )
            else:
                raise
        segs = [WhisperSegment(float(s["start"]), float(s["end"]), s["text"].strip())
                for s in result.get("segments", [])]
        return segs

    elif backend == "cpp":
        # 預留：之後可用 subprocess 呼叫 whisper.cpp 的 CLI，讀回段落再組裝 WhisperSegment
        raise NotImplementedError("backend='cpp' 尚未實作，若需要我可以幫你補上。")

    else:
        raise ValueError(f"未知 backend: {backend}")

def transcribe_with_whisper_by_diar_chunks(
    wav_path: str,
    diar: List[DiarSeg],
    model_size: str = "medium",
    language: str = "zh",
    backend: str = "faster",
    compute_type: str = "int8",
    beam_size: int = 1,
    condition_on_previous_text: bool = False,
    max_chunk_sec: int = 300,
    group_across_speakers: bool = True,
    show_progress: bool = True,
) -> List[WhisperSegment]:
    """
    依語者邊界建立不超過 max_chunk_sec 的 chunk，逐段丟進 transcribe_with_whisper。
    回傳的時間已換算回全局時間軸。
    """
    # 先建 chunk 清單
    chunks = _build_chunks_from_diar(
        diar, max_sec=max_chunk_sec, group_across_speakers=group_across_speakers
    )
    if not chunks:
        return []

    # 讀整檔音訊一次（16k/mono）
    wav, sr = librosa.load(wav_path, sr=SR, mono=True)
    all_segs: List[WhisperSegment] = []

    iterator = chunks if not show_progress else tqdm(chunks, desc="Whisper 轉錄（依語者邊界）", unit="段")
    for (st, ed) in iterator:
        s_idx = max(0, int(st * sr))
        e_idx = min(len(wav), int(ed * sr))
        chunk_wav = wav[s_idx:e_idx].astype(np.float32, copy=False)
        # 轉錄（transcribe_with_whisper 可吃 ndarray）
        segs = transcribe_with_whisper(
            chunk_wav,
            model_size=model_size,
            language=language,
            backend=backend,
            compute_type=compute_type,
            beam_size=beam_size,
            condition_on_previous_text=condition_on_previous_text,
        )
        # 映回全局時間
        for s in segs:
            all_segs.append(WhisperSegment(s.start + st, s.end + st, s.text))
    return all_segs



# =============== 對齊 & 輸出 ===============
def align_whisper_to_speakers(
    whisper_segs: List[WhisperSegment],
    diar: List[DiarSeg],
    show_progress: bool = True,
    tqdm_desc: str = "對齊語者",
) -> List[LabeledSegment]:
    if not diar:
        # 沒有語者資訊，全部 Unknown
        return [LabeledSegment(s.start, s.end, s.text, "Unknown") for s in whisper_segs]

    labeled: List[LabeledSegment] = []
    # 建立說話人編號映射（0->S1, 1->S2, ...）
    uniq = sorted(set(d.label for d in diar))
    to_name = {lab: f"S{idx+1}" for idx, lab in enumerate(uniq)}

    iterator = tqdm(whisper_segs, desc=tqdm_desc, unit="段", total=len(whisper_segs)) if show_progress else whisper_segs

    for seg in iterator:
        best_lb, best_ov = None, 0.0
        for d in diar:
            ov = overlap((seg.start, seg.end), (d.start, d.end))
            if ov > best_ov:
                best_ov = ov
                best_lb = d.label

        if best_lb is None or best_ov == 0.0:
            # 後備：挑最近的語者片段
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



def transcribe_with_diarization(
    input_audio: str,
    model_size: str = "medium",
    language: str = "zh",
    num_speakers: Optional[int] = None,
    show_progress: bool = True,
    backend: str = "faster",           # 新增
    compute_type: str = "int8",        # 新增：只在 faster 後端用得到
):
    """
    整合流程：轉 wav -> resemblyzer 語者分離 -> Whisper 轉錄 -> 對齊 -> 輸出 SRT/TXT
    輸出檔放在 CWD。
    """
    if not os.path.isabs(input_audio):
        input_audio = os.path.join(CWD, input_audio)
    if not os.path.exists(input_audio):
        raise FileNotFoundError(f"找不到音檔: {input_audio}")

    wav_path = ensure_wav_mono16k(input_audio)

    print("[diar] 語者分離（resemblyzer + KMeans）中…")
    diar = diarize_with_resemblyzer(wav_path, num_speakers=num_speakers, show_progress=show_progress)

    print("[whisper] 轉錄中…")
    t = time.time()
    # wsegs = transcribe_with_whisper(
    #     wav_path, model_size=model_size, language=language,
    #     backend=backend, compute_type=compute_type
    # )
    wsegs = transcribe_with_whisper_by_diar_chunks(
        wav_path=wav_path,
        diar=diar,
        model_size=model_size,
        language=language,
        backend=backend,
        compute_type=compute_type,
        max_chunk_sec=300,              # 5 分鐘
        group_across_speakers=True,     # 允許把多個語者片段併成一段，只要切點仍在語者邊界
        show_progress=show_progress,
    )
    
    print(f"耗時 {time.time() - t:.2f} 秒")
    
    print("[align] 對齊段落與說話人…")
    labeled = align_whisper_to_speakers(wsegs, diar, show_progress=show_progress, tqdm_desc="對齊語者")

    file_name = os.path.splitext(os.path.basename(wav_path))[0]
    srt_path = os.path.join(OUTPUT_DIR, f"{file_name}.srt")
    txt_path = os.path.join(OUTPUT_DIR, f"{file_name}.txt")
    write_srt(labeled, srt_path)
    write_txt(labeled, txt_path)

    print(f"已輸出：\n- {srt_path}\n- {txt_path}")
    return labeled


if __name__ == "__main__":
    audio_file = INPUT_FILE 
    transcribe_with_diarization(
        input_audio=audio_file,
        model_size=MODEL,
        language=LANGUAGE,
        num_speakers=SPEAKERS,
        show_progress=True,
        backend="faster",      # 預設就用 faster
        compute_type="int8"    # Apple/CPU 常見高 CP 值設定
    )

