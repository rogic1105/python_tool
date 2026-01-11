# ui.py
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
import os
from src import processor

class DemucsGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Demucs 人聲分離工具 (Mac M1/M2)")
        self.root.geometry("720x450")

        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar(value=os.path.join(os.getcwd(), "output"))
        
        self.create_widgets()

    def create_widgets(self):
        # 1. 輸入區塊
        input_frame = ttk.LabelFrame(self.root, text="輸入設定", padding=10)
        input_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(input_frame, text="音訊檔案:").grid(row=0, column=0, sticky="w")
        ttk.Entry(input_frame, textvariable=self.input_path_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(input_frame, text="瀏覽...", command=self.browse_input).grid(row=0, column=2)

        # 2. 輸出區塊
        output_frame = ttk.LabelFrame(self.root, text="輸出設定", padding=10)
        output_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(output_frame, text="儲存位置:").grid(row=0, column=0, sticky="w")
        ttk.Entry(output_frame, textvariable=self.output_path_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(output_frame, text="瀏覽...", command=self.browse_output).grid(row=0, column=2)

        # 3. 按鈕與進度條區塊
        action_frame = ttk.Frame(self.root, padding=10)
        action_frame.pack(fill="x", padx=10)

        # [新增] 建立一個子容器來並排按鈕
        btn_container = ttk.Frame(action_frame)
        btn_container.pack(fill="x", pady=5)

        # 開始按鈕
        self.btn_run = tk.Button(
            btn_container, 
            text="開始分離人聲", 
            command=self.start_processing, 
            bg="#4CAF50", 
            fg="black", 
            font=("Arial", 12, "bold"),
            height=2,
            width=20
        )
        self.btn_run.pack(side="left", padx=(0, 10), expand=True, fill="x")

        # [新增] 取消按鈕 (預設 disable)
        self.btn_cancel = tk.Button(
            btn_container,
            text="取消",
            command=self.cancel_processing,
            bg="#f44336",  # 紅色
            fg="black",
            font=("Arial", 12, "bold"),
            height=2,
            width=20,
            state="disabled" # 預設無法點擊
        )
        self.btn_cancel.pack(side="right", expand=True, fill="x")

        # 進度條
        self.progress = ttk.Progressbar(action_frame, orient="horizontal", mode="determinate", length=100)
        self.progress.pack(fill="x", pady=5)

        # 4. Log 區塊
        log_frame = ttk.LabelFrame(self.root, text="執行紀錄", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state="disabled", font=("Menlo", 10))
        self.log_text.pack(fill="both", expand=True)

    def browse_input(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Audio Files", "*.mp3 *.wav *.flac *.m4a *.aiff"), ("All Files", "*.*")]
        )
        if file_path:
            self.input_path_var.set(file_path)

    def browse_output(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.output_path_var.set(folder_path)

    def log_message(self, message):
        self.root.after(0, self._append_log, message)

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def update_progress(self, value):
        self.root.after(0, self._set_progress, value)

    def _set_progress(self, value):
        self.progress["value"] = value

    # [新增] 取消功能的邏輯
    def cancel_processing(self):
        if messagebox.askyesno("取消確認", "確定要停止目前的作業嗎？"):
            self.log_message("\n⚠️ 使用者請求取消中...\n")
            # 呼叫 processor 的停止函式
            processor.stop_process()
            # 停用取消按鈕，避免重複點擊
            self.btn_cancel.config(state="disabled")

    def processing_done(self):
        self.root.after(0, self._stop_ui)

    def _stop_ui(self):
        # [修改] 恢復按鈕狀態
        self.btn_run.config(state="normal")      # 啟用開始
        self.btn_cancel.config(state="disabled") # 停用取消
        
        # 這裡我們只顯示完成，如果被取消，log 裡已經有紀錄了，不一定要彈視窗
        # 如果你想區分，可以看 progress 有沒有到 100，或者簡單提示就好
        # messagebox.showinfo("狀態", "作業已結束") 

    def start_processing(self):
        input_path = self.input_path_var.get()
        output_dir = self.output_path_var.get()

        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("錯誤", "請選擇有效的輸入檔案")
            return

        # [修改] UI 狀態切換
        self.btn_run.config(state="disabled")     # 停用開始
        self.btn_cancel.config(state="normal")    # 啟用取消
        
        self.progress["value"] = 0
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")

        processor.run_demucs_thread(
            input_path, 
            output_dir, 
            self.log_message, 
            self.update_progress, 
            self.processing_done
        )