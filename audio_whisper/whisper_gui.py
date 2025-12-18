import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

import sys
import math
import subprocess
import time
import threading
import shutil
from dataclasses import dataclass
from typing import List, Optional, Tuple, Callable
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

import numpy as np
import librosa
import soundfile as sf
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from resemblyzer import VoiceEncoder
from faster_whisper import WhisperModel

# =============== 全域設定 ===============
CWD = os.getcwd()
OUTPUT_DIR_NAME = "data_out"
DATA_OUT = os.path.join(CWD, OUTPUT_DIR_NAME)

if not os.path.exists(DATA_OUT):
    os.makedirs(DATA_OUT)

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

# =============== 核心邏輯 (與 UI 脫鉤) ===============

def log_to_gui(msg: str, callback: Optional[Callable[[str], None]]):
    """Sends log message to GUI if callback exists, else prints to stdout."""
    if callback:
        callback(msg)
    else:
        print(msg)

def ensure_wav_mono16k(input_path: str, output_dir: str) -> str:
    """Converts audio to 16k mono WAV using ffmpeg."""
    base = os.path.splitext(os.path.basename(input_path))[0]
    out_wav = os.path.join(output_dir, f"{base}.wav")
    
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
        out_wav
    ]
    # 隱藏 ffmpeg 輸出
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_wav

def srt_timestamp(t: float) -> str:
    if t < 0: t = 0.0
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = int(t % 60)
    milliseconds = int(round((t - math.floor(t)) * 1000))
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def overlap(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    a0, a1 = a
    b0, b1 = b
    return max(0.0, min(a1, b1) - max(a0, b0))

def compute_window_embeddings(wav: np.ndarray, sr: int) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    encoder = VoiceEncoder()
    # 固定參數
    win_sec = 1.5
    hop_sec = 0.75
    energy_thresh = 0.01

    win_len = int(win_sec * sr)
    hop_len = int(hop_sec * sr)
    
    embeddings = []
    win_times = []

    if len(wav) < win_len:
        pad = np.zeros(win_len - len(wav), dtype=wav.dtype)
        wav = np.concatenate([wav, pad], axis=0)

    # 1. 過濾低能量
    iterator = range(0, len(wav) - win_len + 1, hop_len)
    for start in iterator:
        end = start + win_len
        chunk = wav[start:end]
        rms = float(np.sqrt(np.mean(chunk**2)) + 1e-9)
        if rms < energy_thresh:
            continue
        emb = encoder.embed_utterance(chunk)
        embeddings.append(emb)
        win_times.append((start / sr, end / sr))

    # 2. 若全被過濾，強制取樣
    if not embeddings:
        iterator2 = range(0, len(wav) - win_len + 1, hop_len)
        for start in iterator2:
            end = start + win_len
            chunk = wav[start:end]
            emb = encoder.embed_utterance(chunk)
            embeddings.append(emb)
            win_times.append((start / sr, end / sr))

    return np.stack(embeddings, axis=0), win_times

def cluster_embeddings(embeddings: np.ndarray, num_speakers: int) -> np.ndarray:
    if embeddings.shape[0] == 1:
        return np.zeros((1,), dtype=int)

    if num_speakers > 0:
        km = KMeans(n_clusters=num_speakers, random_state=0, n_init="auto").fit(embeddings)
        return km.labels_
    else:
        # Auto detect k=2..6
        best_k, best_score, best_labels = None, -1.0, None
        k_min = 2
        k_max = min(6, embeddings.shape[0])
        
        for k in range(k_min, k_max + 1):
            km = KMeans(n_clusters=k, random_state=0, n_init="auto").fit(embeddings)
            try:
                score = silhouette_score(embeddings, km.labels_)
            except:
                score = -1.0
            if score > best_score:
                best_k, best_score, best_labels = k, score, km.labels_
        
        if best_labels is None:
            km = KMeans(n_clusters=2, random_state=0, n_init="auto").fit(embeddings)
            return km.labels_
        return best_labels

def merge_contiguous_windows(win_times: List[Tuple[float, float]], labels: np.ndarray) -> List[DiarSeg]:
    if not win_times: return []
    diar = []
    cur_start, cur_end, cur_label = win_times[0][0], win_times[0][1], int(labels[0])
    gap_tol = 0.75 + 1e-6 # hop_sec

    for (st, ed), lb in zip(win_times[1:], labels[1:]):
        lb = int(lb)
        if lb == cur_label and (st - cur_end) <= gap_tol:
            cur_end = ed
        else:
            diar.append(DiarSeg(cur_start, cur_end, cur_label))
            cur_start, cur_end, cur_label = st, ed, lb
    diar.append(DiarSeg(cur_start, cur_end, cur_label))
    return diar

def build_chunks(diar: List[DiarSeg], max_sec=300) -> List[Tuple[float, float]]:
    if not diar: return []
    chunks = []
    cur_st, cur_ed = None, None

    def flush():
        nonlocal cur_st, cur_ed
        if cur_st is not None and cur_ed is not None and cur_ed > cur_st:
            chunks.append((cur_st, cur_ed))
        cur_st, cur_ed = None, None

    for d in diar:
        st, ed = float(d.start), float(d.end)
        length = ed - st
        if length > max_sec:
            flush()
            pos = st
            while pos < ed:
                nxt = min(pos + max_sec, ed)
                chunks.append((pos, nxt))
                pos = nxt
            continue
        
        if cur_st is None:
            cur_st, cur_ed = st, ed
            continue
        
        if (ed - cur_st) <= max_sec:
            cur_ed = ed
        else:
            flush()
            cur_st, cur_ed = st, ed
    flush()
    return chunks

def align_results(whisper_segs: List[WhisperSegment], diar: List[DiarSeg]) -> List[LabeledSegment]:
    if not diar:
        return [LabeledSegment(s.start, s.end, s.text, "Unknown") for s in whisper_segs]
    
    uniq = sorted(set(d.label for d in diar))
    to_name = {lab: f"S{idx+1}" for idx, lab in enumerate(uniq)}
    labeled = []

    for seg in whisper_segs:
        best_lb, best_ov = None, 0.0
        for d in diar:
            ov = overlap((seg.start, seg.end), (d.start, d.end))
            if ov > best_ov:
                best_ov = ov
                best_lb = d.label
        
        if best_lb is None:
            # Fallback
            mid = (seg.start + seg.end) / 2
            nearest = min(diar, key=lambda x: abs((x.start + x.end)/2 - mid))
            best_lb = nearest.label
        
        labeled.append(LabeledSegment(seg.start, seg.end, seg.text, to_name[best_lb]))
    return labeled

# =============== 工作執行緒邏輯 ===============

def run_pipeline(
    input_file: str,
    model_size: str,
    language: str,
    num_speakers: int,
    log_cb: Callable[[str], None],
    progress_cb: Callable[[float, str], None],
    done_cb: Callable[[str, str], None]
):
    try:
        t0 = time.time()
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        
        # 1. Convert
        progress_cb(10, "轉換音訊格式 (ffmpeg)...")
        log_cb(f"正在處理: {input_file}")
        log_cb("正在轉換為 16k Mono WAV...")
        wav_path = ensure_wav_mono16k(input_file, DATA_OUT)
        
        # 2. Diarization
        progress_cb(30, "語者分離運算中 (Resemblyzer)...")
        log_cb("載入音訊做分離分析...")
        wav, sr = librosa.load(wav_path, sr=16000, mono=True)
        
        embeddings, win_times = compute_window_embeddings(wav, sr)
        log_cb(f"計算出 {len(embeddings)} 個語者向量視窗。")
        
        labels = cluster_embeddings(embeddings, num_speakers)
        diar = merge_contiguous_windows(win_times, labels)
        log_cb(f"初步分群完成，共 {len(diar)} 個語音片段。")

        # 3. Transcription
        progress_cb(50, "語音轉錄中 (Whisper)...")
        log_cb(f"載入 Whisper 模型: {model_size} ({language})...")
        
        # 在這裡載入模型一次
        model = WhisperModel(model_size, device="auto", compute_type="int8")
        
        chunks = build_chunks(diar, max_sec=300)
        if not chunks and len(wav) > 0:
            chunks = [(0.0, len(wav)/sr)]
            
        all_segs = []
        total_chunks = len(chunks)
        
        for i, (st, ed) in enumerate(chunks):
            # 計算當前進度百分比 (50% ~ 90%)
            curr_pct = 50 + int((i / total_chunks) * 40)
            progress_cb(curr_pct, f"轉錄中: 片段 {i+1}/{total_chunks}")
            log_cb(f"正在轉錄: {time.strftime('%H:%M:%S', time.gmtime(st))} - {time.strftime('%H:%M:%S', time.gmtime(ed))}")
            
            s_idx = max(0, int(st * sr))
            e_idx = min(len(wav), int(ed * sr))
            chunk_wav = wav[s_idx:e_idx].astype(np.float32, copy=False)
            
            segs, _ = model.transcribe(chunk_wav, language=language, beam_size=1)
            for s in segs:
                all_segs.append(WhisperSegment(s.start + st, s.end + st, s.text.strip()))

        # 4. Align & Write
        progress_cb(95, "對齊與寫入檔案...")
        log_cb("正在對齊語者標籤與文字...")
        labeled = align_results(all_segs, diar)
        
        srt_path = os.path.join(DATA_OUT, f"{base_name}.srt")
        txt_path = os.path.join(DATA_OUT, f"{base_name}.txt")
        
        with open(srt_path, "w", encoding="utf-8") as f:
            for idx, seg in enumerate(labeled, 1):
                f.write(f"{idx}\n{srt_timestamp(seg.start)} --> {srt_timestamp(seg.end)}\n{seg.speaker}: {seg.text}\n\n")
                
        with open(txt_path, "w", encoding="utf-8") as f:
            for seg in labeled:
                f.write(f"[{srt_timestamp(seg.start)} {seg.speaker}] {seg.text}\n")
        
        progress_cb(100, "完成！")
        duration = time.time() - t0
        log_cb(f"全部完成。耗時: {duration:.2f} 秒")
        log_cb(f"輸出 SRT: {srt_path}")
        log_cb(f"輸出 TXT: {txt_path}")
        
        done_cb(srt_path, txt_path)

    except Exception as e:
        log_cb(f"錯誤: {str(e)}")
        import traceback
        log_cb(traceback.format_exc())
        progress_cb(0, "發生錯誤")

# =============== GUI 介面類別 ===============

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("語者分離與轉錄工具 (Native GUI)")
        self.geometry("600x650")
        self.resizable(True, True)
        
        # 變數
        self.file_path = tk.StringVar()
        self.model_size = tk.StringVar(value="medium")
        self.language = tk.StringVar(value="zh")
        self.num_speakers = tk.IntVar(value=0)
        self.is_running = False

        self._build_ui()

    def _build_ui(self):
        # 1. 檔案選擇區
        frame_file = ttk.LabelFrame(self, text="輸入檔案", padding=10)
        frame_file.pack(fill="x", padx=10, pady=5)
        
        entry_file = ttk.Entry(frame_file, textvariable=self.file_path, state="readonly")
        entry_file.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_browse = ttk.Button(frame_file, text="瀏覽...", command=self._browse_file)
        btn_browse.pack(side="right")

        # 2. 參數設定區
        frame_settings = ttk.LabelFrame(self, text="參數設定", padding=10)
        frame_settings.pack(fill="x", padx=10, pady=5)

        # Grid layout for settings
        ttk.Label(frame_settings, text="Whisper 模型:").grid(row=0, column=0, sticky="w", pady=5)
        combo_model = ttk.Combobox(frame_settings, textvariable=self.model_size, state="readonly")
        combo_model['values'] = ("tiny", "base", "small", "medium", "large-v2", "large-v3")
        combo_model.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(frame_settings, text="語言代碼:").grid(row=0, column=2, sticky="w", pady=5, padx=(10, 0))
        combo_lang = ttk.Combobox(frame_settings, textvariable=self.language, state="readonly", width=10)
        combo_lang['values'] = ("zh", "en", "ja", "ko")
        combo_lang.grid(row=0, column=3, sticky="ew", padx=5)

        ttk.Label(frame_settings, text="預估人數 (0=自動):").grid(row=1, column=0, sticky="w", pady=5)
        entry_spk = ttk.Entry(frame_settings, textvariable=self.num_speakers)
        entry_spk.grid(row=1, column=1, sticky="ew", padx=5)

        frame_settings.columnconfigure(1, weight=1)
        frame_settings.columnconfigure(3, weight=1)

        # 3. 執行按鈕
        self.btn_run = ttk.Button(self, text="開始處理", command=self._start_process)
        self.btn_run.pack(fill="x", padx=20, pady=10)

        # 4. 進度條
        self.lbl_progress = ttk.Label(self, text="準備就緒")
        self.lbl_progress.pack(anchor="w", padx=10)
        
        self.progress_bar = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=(0, 10))

        # 5. 日誌區
        lbl_log = ttk.Label(self, text="執行日誌:")
        lbl_log.pack(anchor="w", padx=10)
        
        self.txt_log = scrolledtext.ScrolledText(self, height=15, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 6. 底部資訊
        lbl_footer = ttk.Label(self, text=f"輸出目錄: {DATA_OUT}", foreground="gray")
        lbl_footer.pack(side="bottom", anchor="e", padx=10, pady=5)

    def _browse_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.flac"), ("All Files", "*.*")]
        )
        if path:
            self.file_path.set(path)

    def _log(self, msg):
        """Thread-safe logging to text widget."""
        def _update():
            self.txt_log.config(state="normal")
            self.txt_log.insert("end", msg + "\n")
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")
        self.after(0, _update)

    def _update_progress(self, val, msg):
        """Thread-safe progress update."""
        def _update():
            self.progress_bar["value"] = val
            self.lbl_progress.config(text=f"{msg} ({val}%)")
        self.after(0, _update)

    def _on_done(self, srt_path, txt_path):
        """Thread-safe done callback."""
        def _update():
            self.is_running = False
            self.btn_run.config(state="normal")
            messagebox.showinfo("完成", f"處理完成！\n\nSRT: {os.path.basename(srt_path)}\nTXT: {os.path.basename(txt_path)}")
        self.after(0, _update)

    def _start_process(self):
        if self.is_running:
            return
        
        input_file = self.file_path.get()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("錯誤", "請選擇有效的音檔！")
            return

        # 鎖定 UI
        self.is_running = True
        self.btn_run.config(state="disabled")
        self.txt_log.config(state="normal")
        self.txt_log.delete(1.0, "end")
        self.txt_log.config(state="disabled")
        self.progress_bar["value"] = 0

        # 取得參數
        try:
            spk = int(self.num_speakers.get())
        except ValueError:
            spk = 0
            self.num_speakers.set(0)

        # 開啟執行緒
        t = threading.Thread(
            target=run_pipeline,
            args=(
                input_file,
                self.model_size.get(),
                self.language.get(),
                spk,
                self._log,
                self._update_progress,
                self._on_done
            ),
            daemon=True
        )
        t.start()

if __name__ == "__main__":
    app = App()
    app.mainloop()