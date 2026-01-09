Whisper Speaker Diarization & Transcription (Windows Optimized)
這是一個基於 Python 的本機端語音轉錄與語者分離工具。專案結合了 OpenAI Whisper (透過 faster-whisper 加速) 進行高準確度逐字稿轉錄，並利用 Resemblyzer 進行聲紋分析以區分不同的說話者。

✅ 本版本已針對 Windows 環境進行優化，支援 NVIDIA GPU 加速與穩定性修正。

🌟 功能特色
雙模式介面：提供 GUI (視窗版) 與 CLI (命令列版)，滿足不同使用場景。

Windows GPU 加速：整合 CUDA 支援，使用 NVIDIA 顯卡轉錄速度比 CPU 快 20~50 倍。

自動語者分離：利用深度學習聲紋分析，自動區分並標記說話者 (S1, S2...)。

記憶體優化：修復了 Windows 下模型釋放時的崩潰問題，並採用 int8 / float16 量化技術降低顯存需求。

自動對齊：將分離出的語者標籤與轉錄文字在時間軸上精準對齊。

格式整合：自動輸出 .srt 字幕檔與 .txt 對話紀錄至 data_out 資料夾。

🛠️ 系統架構
程式碼片段

graph TD
    %% 定義樣式
    classDef user fill:#f96,stroke:#333,stroke-width:2px,color:white;
    classDef process fill:#e1f5fe,stroke:#0277bd,stroke-width:2px;
    classDef model fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,stroke-dasharray: 5 5;
    classDef output fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    %% 節點定義
    User([👤 User / 使用者])
    GUI[🖥️ whisper_gui.py]
    CLI[⌨️ whisper_cli_win.py]
    
    subgraph Preprocessing [前置處理]
        FFmpeg[FFmpeg 轉檔]
        WAV(16k Mono WAV)
    end

    subgraph Core [核心運算]
        direction TB
        
        %% 分支 A: 語者分離
        subgraph Diarization [語者分離流程]
            Resemblyzer{{Resemblyzer Model}}
            Embeds[提取聲紋 Embeddings]
            KMeans[KMeans 分群]
            SpkSegs[語者片段 DiarSeg]
        end

        %% 分支 B: 轉錄
        subgraph Transcription [語音轉錄流程]
            Whisper{{Faster-Whisper Model}}
            Chunking[依語者邊界切分]
            TextSegs[文字片段 WhisperSeg]
        end
        
        Align[🔄 Alignment 對齊模組]
    end

    Files[(📂 data_out 資料夾)]
    SRT[📄 .srt 字幕檔]
    TXT[📄 .txt 文字稿]

    %% 流程連接
    User -->|操作介面| GUI
    User -->|命令列參數| CLI
    GUI & CLI -->|輸入音檔| FFmpeg
    FFmpeg --> WAV
    
    %% 核心邏輯
    WAV -->|輸入| Resemblyzer
    Resemblyzer --> Embeds
    Embeds --> KMeans
    KMeans --> SpkSegs
    
    WAV --> Chunking
    SpkSegs -.->|提供切分點| Chunking
    Chunking -->|分段音訊| Whisper
    Whisper --> TextSegs
    
    SpkSegs --> Align
    TextSegs --> Align
    
    %% 輸出
    Align -->|寫入檔案| Files
    Files --> SRT
    Files --> TXT

    %% 套用樣式
    class User user;
    class FFmpeg,WAV,Embeds,KMeans,SpkSegs,Chunking,TextSegs,Align process;
    class Resemblyzer,Whisper model;
    class Files,SRT,TXT output;
⚙️ 安裝需求 (Windows)
1. 安裝 FFmpeg (必要)
本工具依賴 FFmpeg 處理音訊格式。

下載 FFmpeg Windows 版

解壓縮後，將 bin 資料夾路徑加入系統環境變數 Path 中。

驗證方式：在終端機輸入 ffmpeg -version 不應報錯。

2. 安裝 Python 套件
建議使用 Anaconda 或 Python 3.9+ 虛擬環境。

Bash

pip install torch numpy librosa soundfile scikit-learn faster-whisper resemblyzer tqdm
3. 設定 NVIDIA GPU 加速 (關鍵步驟)
要在 Windows 上啟用 GPU 加速，必須手動補齊 faster-whisper (CTranslate2) 所需的 DLL 函式庫。

安裝 CUDA Toolkit：建議安裝 CUDA 11.x 或 12.x 版本。

下載 cuDNN：

前往 NVIDIA cuDNN Archive 下載對應 CUDA 版本的 cuDNN v8.x。

解壓縮，將 bin 資料夾內的所有 .dll 檔案（如 cudnn64_8.dll 等）複製到你的 Python 環境目錄下的 Library\bin (Anaconda) 或 Scripts (venv) 資料夾中。

下載 zlibwapi.dll (極重要)：

Windows 版 cuDNN 依賴此檔案。下載 zlibwapi.dll 並放在與上述 cuDNN DLL 相同的目錄中。

🚀 使用說明
方式一：CLI 命令列 (推薦)
打開 whisper_cli_win.py，編輯最下方的 if __main__ 設定區塊：

Python

if __name__ == "__main__":
    # 輸入檔案路徑
    INPUT_FILE = "data/meeting_recording.m4a"
    
    # 語者人數 (若不確定可設為 None 讓系統自動猜測，但指定人數效果較佳)
    SPEAKERS = 3 
    
    # 模型大小 (tiny, base, small, medium, large-v2, large-v3)
    MODEL = "medium"
    
    # 裝置設定
    # 若已完成上述 GPU 設定，請設為 "cuda"；否則設為 "cpu"
    WHISPER_DEVICE = "cuda"  
    
    # 計算精度
    # 30/40 系列顯卡建議 "float16" (快)；舊顯卡或 CPU 請用 "int8"
    COMPUTE_TYPE = "float16" 

    transcribe_with_diarization(...)
然後在終端機執行：

Bash

python whisper_cli_win.py
方式二：GUI 圖形介面
Bash

python whisper_gui.py
(注意：GUI 版本需確保內部呼叫邏輯已同步更新為 Windows 優化版)

📂 輸出檔案結構
所有輸出的檔案將自動存放於專案目錄下的 data_out 資料夾：

Plaintext

Project/
├── data/               # 放入原始音檔
├── data_out/           # 輸出結果
│   ├── 0108.wav        # 轉換後的 16k 單聲道音檔
│   ├── 0108.srt        # [字幕] 包含時間軸與語者標籤 (S1, S2...)
│   └── 0108.txt        # [文字] 純文字對話紀錄
├── whisper_cli_win.py  # Windows 優化版主程式
└── README.md
📝 常見問題 (Troubleshooting)
Q1: 出現 [WinError 2] 系統找不到指定的檔案 紅字警告？
原因：這是 joblib 在 Windows VS Code 除錯環境下無法正確偵測 CPU 核心數的無害錯誤。

解法：程式碼已內建 os.environ["LOKY_MAX_CPU_COUNT"] = "4" 修復此問題。請確保這行程式碼位於所有 import 之前。

Q2: 出現 [Warning] GPU 初始化失敗... 自動切換至 CPU？
原因：

程式碼中 WHISPER_DEVICE 寫錯 (例如寫成 "gpu" 而非 "cuda")。

缺少 cuDNN 相關 DLL 或 zlibwapi.dll。

解法：請重新檢查「安裝需求」中的第 3 步，確保 DLL 檔案已放入正確路徑。

Q3: 程式跑到 100% 後直接結束，沒有顯示「完成」？
原因：這是 Whisper 模型在釋放記憶體時發生的 Silent Crash。

解法：新版程式碼 (whisper_cli_win.py) 已調整架構，確保在釋放模型前先將檔案寫入硬碟。即使最後崩潰，檔案也已安全儲存於 data_out。

Q4: 轉錄速度很慢？
請確認終端機顯示的是 (cuda, float16)。若是 (cpu, int8)，代表 GPU 加速未成功開啟。Medium 模型在 CPU 上轉錄 1 小時音檔可能需要 30~60 分鐘；GPU 僅需 2~5 分鐘。

📜 License
本專案使用以下開源專案技術：

faster-whisper (MIT)

Resemblyzer (Apache 2.0)