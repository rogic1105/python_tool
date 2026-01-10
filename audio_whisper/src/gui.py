import os
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

# 引入模組化的邏輯與設定
from src.logic import Pipeline, ModelManager
from src.config import DEFAULT_OUTPUT_DIR

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Whisper 語者分離工具 Pro")
        self.geometry("800x750")
        self.resizable(True, True)
        
        self.processor = Pipeline(DEFAULT_OUTPUT_DIR)
        self.is_running = False
        self.is_downloading = False
        self.stop_event = threading.Event()

        # --- UI 變數 ---
        self.file_path = tk.StringVar()
        self.output_path = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.model_size = tk.StringVar(value="medium")
        self.language = tk.StringVar(value="zh")
        self.num_speakers = tk.IntVar(value=0)
        
        # 修改：初始化時取得系統實際路徑
        real_cache_path = ModelManager.get_default_cache_path()
        self.model_path_str = tk.StringVar(value=real_cache_path)
        self.model_status_str = tk.StringVar(value="未知")

        # --- 建構介面 ---
        self._build_ui()

    def _build_ui(self):
        # 1. 頂部設定區
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", padx=10, pady=5)

        # A. 檔案與路徑
        frame_io = ttk.LabelFrame(top_frame, text="1. 檔案與路徑", padding=10)
        frame_io.pack(fill="x", pady=5)
        io_grid = ttk.Frame(frame_io)
        io_grid.pack(fill="x")
        ttk.Label(io_grid, text="輸入音檔:", width=10).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(io_grid, textvariable=self.file_path, state="readonly").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(io_grid, text="選擇檔案", command=self._browse_file).grid(row=0, column=2, padx=5)
        ttk.Label(io_grid, text="輸出目錄:", width=10).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(io_grid, textvariable=self.output_path).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(io_grid, text="變更目錄", command=self._browse_output).grid(row=1, column=2, padx=5)
        io_grid.columnconfigure(1, weight=1)

        # B. 參數設定
        frame_settings = ttk.LabelFrame(top_frame, text="2. 參數設定", padding=10)
        frame_settings.pack(fill="x", pady=5)
        ttk.Label(frame_settings, text="模型:").pack(side="left")
        combo_model = ttk.Combobox(frame_settings, textvariable=self.model_size, state="readonly", width=8)
        combo_model['values'] = ("tiny", "base", "small", "medium", "large-v2", "large-v3")
        combo_model.pack(side="left", padx=5)
        ttk.Label(frame_settings, text="語言:").pack(side="left", padx=(10, 0))
        combo_lang = ttk.Combobox(frame_settings, textvariable=self.language, state="readonly", width=5)
        combo_lang['values'] = ("zh", "en", "ja", "ko")
        combo_lang.pack(side="left", padx=5)
        ttk.Label(frame_settings, text="人數(0自動):").pack(side="left", padx=(10, 0))
        ttk.Entry(frame_settings, textvariable=self.num_speakers, width=5).pack(side="left", padx=5)

        # C. 模型管理
        frame_model = ttk.LabelFrame(top_frame, text="3. 模型管理", padding=10)
        frame_model.pack(fill="x", pady=5)
        
        # 路徑顯示 (唯讀)
        model_row1 = ttk.Frame(frame_model)
        model_row1.pack(fill="x", pady=(0, 5))
        ttk.Label(model_row1, text="儲存位置:").pack(side="left")
        # 這裡會顯示例如 C:\Users\xxx\.cache\huggingface\hub
        ttk.Entry(model_row1, textvariable=self.model_path_str, state="readonly").pack(side="left", fill="x", expand=True, padx=5)
        
        # 下載按鈕
        model_row2 = ttk.Frame(frame_model)
        model_row2.pack(fill="x")
        self.btn_download = ttk.Button(model_row2, text="檢查/下載模型", command=self._download_model_gui)
        self.btn_download.pack(side="left")
        self.lbl_model_status = ttk.Label(model_row2, textvariable=self.model_status_str, foreground="blue")
        self.lbl_model_status.pack(side="left", padx=10)
        self.bar_download = ttk.Progressbar(model_row2, orient="horizontal", mode="indeterminate")
        self.bar_download.pack(side="left", fill="x", expand=True, padx=5)

        # D. 操作按鈕
        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(fill="x", pady=10)
        self.btn_run = ttk.Button(btn_frame, text="開始執行任務", command=self._start_process)
        self.btn_run.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_cancel = ttk.Button(btn_frame, text="取消任務", command=self._cancel_process, state="disabled")
        self.btn_cancel.pack(side="right", fill="x", expand=True, padx=(5, 0))

        # 2. 中間：執行進度
        frame_progress = ttk.LabelFrame(self, text="任務執行進度", padding=10)
        frame_progress.pack(fill="x", padx=10, pady=5)
        self.lbl_p1 = ttk.Label(frame_progress, text="步驟 1: 格式轉換", foreground="gray"); self.lbl_p1.pack(anchor="w")
        self.bar_p1 = ttk.Progressbar(frame_progress, orient="horizontal", mode="determinate"); self.bar_p1.pack(fill="x", pady=(0, 5))
        self.lbl_p2 = ttk.Label(frame_progress, text="步驟 2: 語者分析", foreground="gray"); self.lbl_p2.pack(anchor="w")
        self.bar_p2 = ttk.Progressbar(frame_progress, orient="horizontal", mode="determinate"); self.bar_p2.pack(fill="x", pady=(0, 5))
        self.lbl_p3 = ttk.Label(frame_progress, text="步驟 3: 語音轉錄", foreground="gray"); self.lbl_p3.pack(anchor="w")
        self.bar_p3 = ttk.Progressbar(frame_progress, orient="horizontal", mode="determinate"); self.bar_p3.pack(fill="x", pady=(0, 5))

        # 3. 底部：系統資訊與內容 (1:2)
        paned_window = ttk.PanedWindow(self, orient="horizontal")
        paned_window.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        frame_sys = ttk.LabelFrame(paned_window, text="系統資訊", padding=5)
        paned_window.add(frame_sys, weight=1)
        self.txt_sys_log = scrolledtext.ScrolledText(frame_sys, width=30, state="disabled", font=("Consolas", 9))
        self.txt_sys_log.pack(fill="both", expand=True)
        frame_content = ttk.LabelFrame(paned_window, text="目前轉錄內容", padding=5)
        paned_window.add(frame_content, weight=2)
        self.txt_content = scrolledtext.ScrolledText(frame_content, width=60, state="disabled", font=("Microsoft JhengHei", 10))
        self.txt_content.pack(fill="both", expand=True)

        self.lbl_footer = ttk.Label(self, text=f"準備就緒", foreground="gray")
        self.lbl_footer.pack(side="bottom", anchor="w", padx=10, pady=2)

    def _browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.flac"), ("All Files", "*.*")])
        if path: self.file_path.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory()
        if path: self.output_path.set(path)

    # --- 模型下載邏輯 ---
    def _download_model_gui(self):
        if self.is_running or self.is_downloading: return
        
        target_model = self.model_size.get()
        self.is_downloading = True
        self.btn_download.config(state="disabled")
        self.btn_run.config(state="disabled")
        self.bar_download.start(10) 
        self.model_status_str.set(f"正在檢查/下載: {target_model}...")

        def _dl_worker():
            try:
                ModelManager.download(target_model)
                self.after(0, lambda: self._on_download_finish("已就緒", False))
            except Exception as e:
                self.after(0, lambda: self._on_download_finish(f"錯誤: {str(e)}", True))

        threading.Thread(target=_dl_worker, daemon=True).start()

    def _on_download_finish(self, status_msg, is_error):
        self.bar_download.stop()
        self.is_downloading = False
        self.btn_download.config(state="normal")
        if not self.is_running:
            self.btn_run.config(state="normal")
        
        self.model_status_str.set(status_msg)
        if is_error:
            messagebox.showerror("下載失敗", status_msg)
        else:
            self._log_sys(f"模型檢查完畢: {status_msg}")

    # --- 任務控制 ---
    def _cancel_process(self):
        if self.is_running:
            if messagebox.askyesno("取消", "確定要終止任務嗎？"):
                self.stop_event.set()
                self.btn_cancel.config(state="disabled")
                self._log_sys("正在取消中...")

    def _start_process(self):
        if self.is_running or self.is_downloading: return
        f = self.file_path.get()
        out = self.output_path.get()
        if not f or not os.path.exists(f): return messagebox.showwarning("警告", "請選擇檔案")
        if not out: return messagebox.showwarning("警告", "請指定輸出路徑")

        self.is_running = True
        self.stop_event.clear()
        self.btn_run.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self._reset_ui()
        self._log_sys(f"輸出路徑: {out}")
        
        try: spk = self.num_speakers.get()
        except: spk = 0

        threading.Thread(target=self._worker, args=(f, self.model_size.get(), self.language.get(), spk, out), daemon=True).start()

    def _worker(self, fpath, model, lang, spk, out_dir):
        try:
            srt, txt = self.processor.run(
                input_path=fpath, model_size=model, lang=lang, speakers=spk,
                log_cb=self._log_sys, progress_cb=self._update_progress, transcript_cb=self._log_content,
                stop_event=self.stop_event, custom_output_dir=out_dir
            )
            self._on_done(srt)
        except RuntimeError as re:
            self._log_sys(f"[Info] {re}")
            self.after(0, lambda: [self.btn_run.config(state="normal"), self.btn_cancel.config(state="disabled"), self.btn_download.config(state="normal"), self.lbl_footer.config(text="任務已取消")])
            self.is_running = False
        except Exception as e:
            err = str(e)
            self._log_sys(f"[Error] {err}")
            self.after(0, lambda: [self.btn_run.config(state="normal"), self.btn_cancel.config(state="disabled"), self.btn_download.config(state="normal"), messagebox.showerror("錯誤", err)])
            self.is_running = False

    def _on_done(self, srt):
        def _act():
            self.is_running = False
            self.btn_run.config(state="normal")
            self.btn_cancel.config(state="disabled")
            self.btn_download.config(state="normal")
            self.lbl_footer.config(text=f"完成: {srt}")
            messagebox.showinfo("完成", "處理完畢！")
        self.after(0, _act)

    def _log_sys(self, msg):
        self.after(0, lambda: [self.txt_sys_log.config(state="normal"), self.txt_sys_log.insert("end", f"> {msg}\n"), self.txt_sys_log.see("end"), self.txt_sys_log.config(state="disabled")])

    def _log_content(self, text):
        self.after(0, lambda: [self.txt_content.config(state="normal"), self.txt_content.insert("end", text + "\n"), self.txt_content.see("end"), self.txt_content.config(state="disabled")])

    def _update_progress(self, stage, val, msg=None):
        def _up():
            if stage == 1: self.bar_p1["value"] = val; self.lbl_p1.config(foreground="green" if val >= 100 else "blue")
            elif stage == 2: self.bar_p2["value"] = val; self.lbl_p2.config(foreground="green" if val >= 100 else "blue")
            elif stage == 3: self.bar_p3["value"] = val; txt=f"步驟 3: 語音轉錄 ({int(val)}%)"; self.lbl_p3.config(text=txt + (f" - {msg}" if msg else ""), foreground="green" if val >= 100 else "blue")
        self.after(0, _up)

    def _reset_ui(self):
        self.bar_p1["value"] = 0; self.lbl_p1.config(foreground="gray")
        self.bar_p2["value"] = 0; self.lbl_p2.config(foreground="gray")
        self.bar_p3["value"] = 0; self.lbl_p3.config(foreground="gray", text="步驟 3: 語音轉錄")
        self.txt_sys_log.config(state="normal"); self.txt_sys_log.delete(1.0, "end"); self.txt_sys_log.config(state="disabled")
        self.txt_content.config(state="normal"); self.txt_content.delete(1.0, "end"); self.txt_content.config(state="disabled")

if __name__ == "__main__":
    app = App()
    app.mainloop()