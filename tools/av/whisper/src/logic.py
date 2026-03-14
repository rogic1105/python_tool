import os
import time
import threading
import numpy as np
import soundfile as sf
from typing import List, Tuple, Callable, Optional
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from resemblyzer import VoiceEncoder
from faster_whisper import WhisperModel

from .config import SYSTEM, SR, WIN_SEC, HOP_SEC, ENERGY_THRESH
from .utils import DiarSeg, WhisperSegment, LabeledSegment


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _check_cancel(stop_event: Optional[threading.Event]):
    if stop_event and stop_event.is_set():
        raise RuntimeError("使用者已取消任務")


# ──────────────────────────────────────────────────────────────────────────────
# Speaker Diarization
# ──────────────────────────────────────────────────────────────────────────────

class DiarizationEngine:
    @staticmethod
    def compute_embeddings(
        wav: np.ndarray,
        sr: int,
        progress_callback=None,
        stop_event: Optional[threading.Event] = None,
    ) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
        encoder = VoiceEncoder(device="cpu")
        win_len = int(WIN_SEC * sr)
        hop_len = int(HOP_SEC * sr)
        embeddings, win_times = [], []

        if len(wav) < win_len:
            wav = np.concatenate([wav, np.zeros(win_len - len(wav), dtype=wav.dtype)])

        total_steps = (len(wav) - win_len) // hop_len + 1

        for i, start in enumerate(range(0, len(wav) - win_len + 1, hop_len)):
            _check_cancel(stop_event)
            if progress_callback and i % 50 == 0:
                progress_callback((i / total_steps) * 100)
            end = start + win_len
            chunk = wav[start:end]
            if np.mean(np.abs(chunk)) < ENERGY_THRESH:
                continue
            embeddings.append(encoder.embed_utterance(chunk))
            win_times.append((start / sr, end / sr))

        # fallback: use all windows if energy filter removed everything
        if not embeddings:
            for start in range(0, len(wav) - win_len + 1, hop_len):
                _check_cancel(stop_event)
                end = start + win_len
                embeddings.append(encoder.embed_utterance(wav[start:end]))
                win_times.append((start / sr, end / sr))

        return np.stack(embeddings, axis=0), win_times

    @staticmethod
    def cluster(embeddings: np.ndarray, num_speakers: int = 0) -> np.ndarray:
        if embeddings.shape[0] <= 1:
            return np.zeros(embeddings.shape[0], dtype=int)
        if num_speakers > 0:
            return KMeans(n_clusters=num_speakers, random_state=42, n_init="auto").fit(embeddings).labels_
        best_k, best_score, best_labels = None, -1.0, None
        for k in range(2, min(6, embeddings.shape[0]) + 1):
            km = KMeans(n_clusters=k, random_state=42, n_init="auto").fit(embeddings)
            try:
                score = silhouette_score(embeddings, km.labels_)
            except Exception:
                score = -1.0
            if score > best_score:
                best_k, best_score, best_labels = k, score, km.labels_
        return best_labels if best_labels is not None else np.zeros(embeddings.shape[0], dtype=int)


# ──────────────────────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────────────────────

class Pipeline:
    def __init__(self, default_output_dir: str):
        self.default_output_dir = default_output_dir

    def _load_model(self, model_size: str) -> Tuple[WhisperModel, str]:
        if SYSTEM == "Windows":
            try:
                return WhisperModel(model_size, device="cuda", compute_type="float16"), "cuda"
            except Exception:
                return WhisperModel(model_size, device="cpu", compute_type="int8"), "cpu"
        return WhisperModel(model_size, device="cpu", compute_type="int8"), "cpu"

    def run(
        self,
        input_path: str,
        model_size: str,
        lang: str,
        speakers: int,
        log_cb: Callable[[str], None],
        progress_cb: Callable[[int, float, Optional[str]], None],
        transcript_cb: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        custom_output_dir: Optional[str] = None,
    ) -> Tuple[str, str]:
        from .utils import ensure_wav_mono16k, srt_timestamp, align_segments_stream

        # ── Output directory ──────────────────────────────────────────
        out_dir = custom_output_dir or self.default_output_dir
        if not out_dir:
            raise RuntimeError("輸出目錄未指定，請在介面中設定輸出路徑。")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"無法建立輸出目錄: {e}\n路徑: {out_dir}") from e

        t_start = time.time()

        # ── Step 1: Format conversion ─────────────────────────────────
        _check_cancel(stop_event)
        log_cb(f"開始處理: {os.path.basename(input_path)}")
        progress_cb(1, 10, "轉檔中...")
        wav_path = ensure_wav_mono16k(input_path, out_dir)
        progress_cb(1, 100, "完成")

        # ── Step 2: Speaker diarization ───────────────────────────────
        _check_cancel(stop_event)
        log_cb("讀取音訊與分析語者特徵...")
        wav, sr = sf.read(wav_path)
        if sr != SR:
            import librosa
            wav = librosa.resample(wav, orig_sr=sr, target_sr=SR)

        embeddings, times = DiarizationEngine.compute_embeddings(
            wav, SR, lambda pct: progress_cb(2, pct, None), stop_event
        )
        log_cb(f"進行語者分群... {len(embeddings)} 個片段")
        labels = DiarizationEngine.cluster(embeddings, speakers)
        progress_cb(2, 100, "完成")

        # ── Step 3: Transcription ─────────────────────────────────────
        _check_cancel(stop_event)
        log_cb("載入 Whisper 模型...")
        model, device_used = self._load_model(model_size)
        log_cb(f"模型載入完成: {device_used}")

        # Standard approach: pass WAV path directly so faster-whisper
        # handles internal 30-second windowing with proper overlap.
        # initial_prompt helps maintain the target language/script.
        initial_prompt = "以下是普通話語音。" if lang == "zh" else None

        log_cb("開始語音識別...")
        segs, info = model.transcribe(
            wav_path,
            language=lang,
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "threshold": 0.02,           # 歌聲信心分數低（~0.1），需更低門檻
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 1000,       # 結尾段落補足 padding
            },
            no_speech_threshold=0.3,         # 預設 0.6 太嚴，歌曲後段容易被跳過
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
        )

        audio_duration = info.duration if info.duration else (len(wav) / SR)
        log_cb(f"音訊時長: {audio_duration:.1f}s  |  偵測語言: {info.language} ({info.language_probability:.0%})")

        all_whisper_segs: List[WhisperSegment] = []
        for s in segs:
            _check_cancel(stop_event)
            seg_text = s.text.strip()
            if not seg_text:
                continue
            all_whisper_segs.append(WhisperSegment(s.start, s.end, seg_text))
            pct = min(s.end / audio_duration * 100, 99) if audio_duration > 0 else 0
            progress_cb(3, pct, f"{s.end:.0f}/{audio_duration:.0f}s")
            # Real-time preview (no speaker label yet)
            if transcript_cb:
                transcript_cb(f"[{srt_timestamp(s.start)}] {seg_text}")

        progress_cb(3, 100, "完成")
        log_cb(f"語音識別完成，共 {len(all_whisper_segs)} 個有效段落")
        if not all_whisper_segs:
            log_cb("⚠ 警告：未識別到任何語音，輸出將為空白。")
            log_cb("  可能原因：語言設定錯誤、音訊過靜、或模型無法解碼。")

        # ── Step 4: Streaming alignment + incremental file write ─────────
        _check_cancel(stop_event)
        log_cb("對齊語者標記並寫入檔案...")

        base = os.path.splitext(os.path.basename(input_path))[0]
        srt_path = os.path.join(out_dir, f"{base}.srt")
        txt_path = os.path.join(out_dir, f"{base}.txt")
        log_cb(f"輸出目錄: {out_dir}")

        # Clear content panel before repopulating with speaker labels
        if transcript_cb:
            transcript_cb(None)

        try:
            srt_f = open(srt_path, "w", encoding="utf-8")
            txt_f = open(txt_path, "w", encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"無法建立輸出檔案: {e}") from e

        written = 0
        try:
            for i, s in enumerate(align_segments_stream(all_whisper_segs, times, labels), 1):
                _check_cancel(stop_event)
                line_srt = f"{i}\n{srt_timestamp(s.start)} --> {srt_timestamp(s.end)}\n{s.speaker}: {s.text}\n\n"
                line_txt = f"[{srt_timestamp(s.start)} {s.speaker}] {s.text}\n"
                srt_f.write(line_srt)
                srt_f.flush()
                txt_f.write(line_txt)
                txt_f.flush()
                written += 1
                if transcript_cb:
                    transcript_cb(f"[{srt_timestamp(s.start)} {s.speaker}] {s.text}")
        finally:
            srt_f.close()
            txt_f.close()

        log_cb(f"SRT 寫入完成，共 {written} 段 ({os.path.getsize(srt_path)} bytes)")
        log_cb(f"TXT 寫入完成 ({os.path.getsize(txt_path)} bytes)")

        log_cb(f"全部完成！耗時: {time.time() - t_start:.2f} 秒")
        return srt_path, txt_path
