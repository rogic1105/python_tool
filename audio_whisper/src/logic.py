import os
import time
import threading
import numpy as np
import soundfile as sf
from typing import List, Tuple, Callable, Optional
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from resemblyzer import VoiceEncoder
from faster_whisper import WhisperModel, download_model

# 新增：引入 HuggingFace 常數以取得真實路徑
try:
    from huggingface_hub.constants import HF_HUB_CACHE
except ImportError:
    # 後備方案 (雖然安裝 faster-whisper 通常會有這個套件)
    HF_HUB_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")

# 引入設定
from src.config import SYSTEM, SR, WIN_SEC, HOP_SEC, ENERGY_THRESH, MODEL_CACHE_DIR
from src.utils import DiarSeg, WhisperSegment, LabeledSegment

# ==========================================
# 模型管理器
# ==========================================
class ModelManager:
    @staticmethod
    def get_default_cache_path() -> str:
        """回傳 HuggingFace Hub 的系統預設快取路徑"""
        return str(HF_HUB_CACHE)

    @staticmethod
    def download(model_size: str, progress_cb: Callable = None):
        """執行模型下載 (使用系統預設路徑)"""
        if progress_cb: progress_cb("檢查/下載中...")
        
        # cache_dir=None 代表使用系統預設
        model_path = download_model(model_size, cache_dir=None)
        
        if progress_cb: progress_cb("就緒")
        return model_path

# ==========================================
# 核心邏輯 (Pipeline)
# ==========================================
class DiarizationEngine:
    @staticmethod
    def compute_embeddings(wav: np.ndarray, sr: int, 
                           progress_callback=None, 
                           stop_event: Optional[threading.Event] = None) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
        encoder = VoiceEncoder(device="cpu")
        win_len = int(WIN_SEC * sr)
        hop_len = int(HOP_SEC * sr)
        
        embeddings = []
        win_times = []

        if len(wav) < win_len:
            pad = np.zeros(win_len - len(wav), dtype=wav.dtype)
            wav = np.concatenate([wav, pad], axis=0)

        total_steps = (len(wav) - win_len) // hop_len + 1
        iterator = range(0, len(wav) - win_len + 1, hop_len)
        
        for i, start in enumerate(iterator):
            if stop_event and stop_event.is_set():
                raise RuntimeError("使用者已取消任務")

            if progress_callback and i % 50 == 0:
                pct = (i / total_steps) * 100
                progress_callback(pct)

            end = start + win_len
            chunk = wav[start:end]
            if np.mean(np.abs(chunk)) < ENERGY_THRESH:
                continue
            embeddings.append(encoder.embed_utterance(chunk))
            win_times.append((start / sr, end / sr))

        if not embeddings:
            for start in range(0, len(wav) - win_len + 1, hop_len):
                if stop_event and stop_event.is_set(): raise RuntimeError("使用者已取消任務")
                end = start + win_len
                embeddings.append(encoder.embed_utterance(wav[start:end]))
                win_times.append((start / sr, end / sr))

        return np.stack(embeddings, axis=0), win_times

    @staticmethod
    def cluster(embeddings: np.ndarray, num_speakers: int = 0) -> np.ndarray:
        if embeddings.shape[0] <= 1:
            return np.zeros((embeddings.shape[0],), dtype=int)

        if num_speakers > 0:
            return KMeans(n_clusters=num_speakers, random_state=42, n_init="auto").fit(embeddings).labels_
        
        best_k, best_score, best_labels = None, -1.0, None
        max_k = min(6, embeddings.shape[0])
        for k in range(2, max_k + 1):
            km = KMeans(n_clusters=k, random_state=42, n_init="auto").fit(embeddings)
            try: score = silhouette_score(embeddings, km.labels_)
            except: score = -1.0
            if score > best_score:
                best_k, best_score, best_labels = k, score, km.labels_
        return best_labels if best_labels is not None else np.zeros((embeddings.shape[0],), dtype=int)

class Pipeline:
    def __init__(self, default_output_dir: str):
        self.default_output_dir = default_output_dir

    def _load_model_optimized(self, model_size):
        if SYSTEM == "Windows":
            try:
                return WhisperModel(model_size, device="cuda", compute_type="float16"), "cuda"
            except:
                return WhisperModel(model_size, device="cpu", compute_type="int8"), "cpu"
        else:
            return WhisperModel(model_size, device="cpu", compute_type="int8"), "cpu"

    def run(self, input_path: str, model_size: str, lang: str, speakers: int, 
            log_cb: Callable[[str], None], 
            progress_cb: Callable[[int, float, Optional[str]], None],
            transcript_cb: Optional[Callable[[str], None]] = None,
            stop_event: Optional[threading.Event] = None,
            custom_output_dir: Optional[str] = None
            ) -> Tuple[str, str]:
        
        from src.utils import ensure_wav_mono16k, srt_timestamp, build_chunks, align_segments
        
        out_dir = custom_output_dir if custom_output_dir else self.default_output_dir
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        t_start = time.time()
        
        # Stage 1: Convert
        if stop_event and stop_event.is_set(): raise RuntimeError("使用者已取消任務")
        log_cb(f"開始處理: {os.path.basename(input_path)}")
        progress_cb(1, 10, "轉檔中...")
        wav_path = ensure_wav_mono16k(input_path, out_dir)
        progress_cb(1, 100, "完成")
        
        # Stage 2: Diarize
        if stop_event and stop_event.is_set(): raise RuntimeError("使用者已取消任務")
        log_cb("讀取音訊與分析語者特徵...")
        wav, sr = sf.read(wav_path)
        if sr != SR: 
            import librosa
            wav = librosa.resample(wav, orig_sr=sr, target_sr=SR)
        
        def diar_progress(pct):
            progress_cb(2, pct, None)

        embeddings, times = DiarizationEngine.compute_embeddings(wav, SR, diar_progress, stop_event)
        
        log_cb(f"進行分群 (Clustering)... {len(embeddings)} 個片段")
        labels = DiarizationEngine.cluster(embeddings, speakers)
        progress_cb(2, 100, "完成")
        
        # Stage 3: Transcribe
        if stop_event and stop_event.is_set(): raise RuntimeError("使用者已取消任務")
        log_cb("載入 Whisper 模型...")
        model, device_used = self._load_model_optimized(model_size)
        log_cb(f"模型載入完成: {device_used}")

        chunks = build_chunks(times, labels)
        if not chunks and len(wav) > 0: chunks = [(0.0, len(wav)/SR)]

        all_whisper_segs = []
        total_chunks = len(chunks)
        
        for i, (st, ed) in enumerate(chunks):
            if stop_event and stop_event.is_set():
                del model
                raise RuntimeError("使用者已取消任務")

            pct = ((i + 1) / total_chunks) * 100
            progress_cb(3, pct, f"{i+1}/{total_chunks}")
            
            s_idx = int(st * SR)
            e_idx = int(ed * SR)
            chunk_wav = wav[s_idx:e_idx].astype(np.float32)
            
            segs, _ = model.transcribe(
                chunk_wav, language=lang, beam_size=1, 
                vad_filter=False, condition_on_previous_text=False
            )
            
            for s in segs:
                seg_text = s.text.strip()
                all_whisper_segs.append(WhisperSegment(s.start + st, s.end + st, seg_text))
                if transcript_cb and seg_text:
                    transcript_cb(f"[{srt_timestamp(s.start + st)}] {seg_text}")

        del model
        
        # Finalize
        if stop_event and stop_event.is_set(): raise RuntimeError("使用者已取消任務")
        log_cb("正在對齊語者與輸出檔案...")
        labeled = align_segments(all_whisper_segs, times, labels)

        base = os.path.splitext(os.path.basename(input_path))[0]
        srt_path = os.path.join(out_dir, f"{base}.srt")
        txt_path = os.path.join(out_dir, f"{base}.txt")
        
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, s in enumerate(labeled, 1):
                f.write(f"{i}\n{srt_timestamp(s.start)} --> {srt_timestamp(s.end)}\n{s.speaker}: {s.text}\n\n")
                
        with open(txt_path, "w", encoding="utf-8") as f:
            for s in labeled:
                f.write(f"[{srt_timestamp(s.start)} {s.speaker}] {s.text}\n")
        
        log_cb(f"全部完成! 耗時: {time.time() - t_start:.2f} 秒")
        return srt_path, txt_path