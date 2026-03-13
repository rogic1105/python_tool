import os
import time
import threading
from typing import Callable, Optional, Tuple

from .config import SYSTEM
from .utils import LabeledSegment, srt_timestamp, ensure_wav_mono16k, normalize_speaker


def _check_cancel(stop_event: Optional[threading.Event]):
    if stop_event and stop_event.is_set():
        raise RuntimeError("使用者已取消任務")


class Pipeline:
    def __init__(self, default_output_dir: str):
        self.default_output_dir = default_output_dir

    def _detect_device(self) -> Tuple[str, str]:
        if SYSTEM == "Windows":
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda", "float16"
            except Exception:
                pass
        elif SYSTEM == "Darwin":
            try:
                import torch
                if torch.backends.mps.is_available():
                    return "mps", "float32"
            except Exception:
                pass
        return "cpu", "int8"

    def run(
        self,
        input_path: str,
        model_size: str,
        lang: str,
        speakers: int,
        hf_token: str,
        batch_size: int,
        log_cb: Callable[[str], None],
        progress_cb: Callable[[int, float, Optional[str]], None],
        transcript_cb: Optional[Callable] = None,
        stop_event: Optional[threading.Event] = None,
        custom_output_dir: Optional[str] = None,
    ) -> Tuple[str, str]:
        import whisperx

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

        # ── Step 2: Transcription + Alignment ─────────────────────────
        _check_cancel(stop_event)
        device, compute_type = self._detect_device()
        log_cb(f"載入 WhisperX 模型（{model_size}，{device}/{compute_type}）...")
        progress_cb(2, 5, "載入模型...")

        transcribe_lang = lang if lang != "auto" else None
        model = whisperx.load_model(
            model_size,
            device,
            compute_type=compute_type,
            language=transcribe_lang,
        )

        _check_cancel(stop_event)
        log_cb("讀取音訊...")
        progress_cb(2, 15, "讀取音訊...")
        audio = whisperx.load_audio(wav_path)

        _check_cancel(stop_event)
        log_cb(f"批次轉錄中（batch_size={batch_size}）...")
        progress_cb(2, 20, "轉錄中...")
        result = model.transcribe(audio, batch_size=batch_size)
        detected_lang = result.get("language", lang or "zh")
        log_cb(f"偵測語言: {detected_lang}，共 {len(result['segments'])} 個片段")
        progress_cb(2, 60, "轉錄完成，對齊中...")

        # Alignment (word-level timestamps)
        _check_cancel(stop_event)
        try:
            log_cb(f"載入對齊模型（{detected_lang}）...")
            model_a, metadata = whisperx.load_align_model(
                language_code=detected_lang, device=device
            )
            result = whisperx.align(
                result["segments"], model_a, metadata, audio, device,
                return_char_alignments=False,
            )
            log_cb("對齊完成（word-level timestamps）")
        except Exception as e:
            log_cb(f"⚠ 對齊失敗（{e}），使用原始時間戳")
        progress_cb(2, 100, "完成")

        # Real-time preview (no speaker yet)
        if transcript_cb:
            for seg in result["segments"]:
                _check_cancel(stop_event)
                text = seg.get("text", "").strip()
                if text:
                    transcript_cb(f"[{srt_timestamp(seg['start'])}] {text}")

        # ── Step 3: Diarization ───────────────────────────────────────
        _check_cancel(stop_event)
        progress_cb(3, 0, "語者分離...")

        if hf_token:
            try:
                log_cb("語者分離中（pyannote.audio）...")
                diarize_model = whisperx.DiarizationPipeline(
                    use_auth_token=hf_token, device=device
                )
                kwargs = {}
                if speakers > 0:
                    kwargs["min_speakers"] = speakers
                    kwargs["max_speakers"] = speakers
                diarize_segments = diarize_model(audio, **kwargs)
                result = whisperx.assign_word_speakers(diarize_segments, result)
                log_cb("語者分離完成")
            except Exception as e:
                log_cb(f"⚠ 語者分離失敗（{e}），標記為 Unknown")
        else:
            log_cb("未提供 HF Token，跳過語者分離（標記為 Unknown）")
        progress_cb(3, 100, "完成")

        # ── Step 4: Write files ───────────────────────────────────────
        _check_cancel(stop_event)
        log_cb("對齊語者標記並寫入檔案...")

        base = os.path.splitext(os.path.basename(input_path))[0]
        srt_path = os.path.join(out_dir, f"{base}.srt")
        txt_path = os.path.join(out_dir, f"{base}.txt")
        log_cb(f"輸出目錄: {out_dir}")

        # Clear content panel, repopulate with speaker labels
        if transcript_cb:
            transcript_cb(None)

        try:
            srt_f = open(srt_path, "w", encoding="utf-8")
            txt_f = open(txt_path, "w", encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"無法建立輸出檔案: {e}") from e

        speaker_map = {}
        written = 0
        try:
            for seg in result["segments"]:
                _check_cancel(stop_event)
                text = seg.get("text", "").strip()
                if not text:
                    continue
                raw_speaker = seg.get("speaker", "Unknown")
                speaker = normalize_speaker(raw_speaker, speaker_map) if raw_speaker != "Unknown" else "Unknown"
                start, end = seg["start"], seg["end"]

                written += 1
                line_srt = f"{written}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{speaker}: {text}\n\n"
                line_txt = f"[{srt_timestamp(start)} {speaker}] {text}\n"
                srt_f.write(line_srt)
                srt_f.flush()
                txt_f.write(line_txt)
                txt_f.flush()
                if transcript_cb:
                    transcript_cb(f"[{srt_timestamp(start)} {speaker}] {text}")
        finally:
            srt_f.close()
            txt_f.close()

        log_cb(f"SRT 寫入完成，共 {written} 段 ({os.path.getsize(srt_path)} bytes)")
        log_cb(f"TXT 寫入完成 ({os.path.getsize(txt_path)} bytes)")
        log_cb(f"全部完成！耗時: {time.time() - t_start:.2f} 秒")
        return srt_path, txt_path
