這份 `README.md` 需要大幅更新，因為您上傳的程式碼結構已經從單純的腳本演變成了**具備圖形介面 (GUI)** 的應用程式 (`main.py` 啟動 UI，`separate_audio.py` 才是獨立腳本)。

原本的 README 還停留在「請把這段 code 存成 main.py」的階段，現在應該要改成「如何使用這個 GUI 工具」。

以下是幫您重新編寫、完善後的 `README.md`。它涵蓋了 GUI 操作、CLI 腳本使用方式，以及針對 Apple Silicon 的環境設定。

---

# Audio Separation Tool (Demucs GUI for macOS)

這是一個專為 **Apple Silicon (M1/M2/M3)** 優化的音訊分離工具，基於 Meta 的 **Demucs (Hybrid Transformer)** 模型。

本專案提供了一個直覺的 **圖形介面 (GUI)**，讓你可以輕鬆選擇檔案、分離人聲與伴奏，並自動整理輸出資料夾結構。

## ✨ 特色 (Features)

* **圖形化介面**: 免去輸入指令的麻煩，直接瀏覽檔案即可操作。
* **即時進度顯示**: 具備進度條與詳細執行紀錄 (Log)，隨時掌握處理狀況。
* **自動整理檔案**: 程式會自動將 Demucs 複雜的輸出路徑 (`output/htdemucs/song_name/...`) 簡化為直觀的資料夾結構。
* **支援中途取消**: 誤按或想更換檔案時，可隨時停止作業。
* **Apple Silicon 優化**: 針對 Mac M 系列晶片調整環境配置。

---

## 📋 環境需求 (Prerequisites)

* **OS**: macOS (建議使用 Apple Silicon M1/M2/M3 以獲得最佳效能)
* **Python**: 3.10 (推薦)
* **Package Manager**: Anaconda 或 Miniconda

---

## 🛠 安裝指南 (Installation Guide)

請開啟 Terminal (終端機)，依序執行以下指令來建立環境。

### 1. 建立 Conda 環境

```bash
# 建立名為 demucs-env 的環境，指定 Python 3.10
conda create -n demucs-env python=3.10 -y

# 啟用環境
conda activate demucs-env

```

### 2. 安裝 FFmpeg (必要!)

Demucs 需要 FFmpeg 來處理音訊檔案的讀寫。

```bash
conda install -c conda-forge ffmpeg -y

```

### 3. 安裝 Python 依賴

```bash
# 安裝 Demucs 主程式
pip install demucs

# 安裝 Tkinter (通常 Python 內建，但若報錯可執行此行)
# conda install tk -y

```

### 4. 修復 Mac 環境相容性問題 (重要!)

最新的 `torchaudio` 與 macOS 有部分相容性問題，請執行以下指令進行降級與修復，以避免 `TorchCodec` 錯誤：

```bash
# 1. 降級 Torchaudio 以避開新版 bug
pip install torch==2.5.1 torchaudio==2.5.1

# 2. 安裝 SoundFile 音訊後端
pip install soundfile

```

---

## 🚀 使用方法 (Usage)

本工具提供兩種使用方式：**GUI 圖形介面 (推薦)** 與 **CLI 腳本模式**。

### 方法一：啟動圖形介面 (GUI Mode)

這是最簡單的使用方式。

1. 確認終端機已進入專案資料夾，且已啟用環境 (`conda activate demucs-env`)。
2. 執行主程式：
```bash
python main.py

```


3. **操作步驟**：
* 點擊 **「瀏覽...」** 選擇你的音訊檔案 (`.mp3`, `.wav`, `.m4a` 等)。
* 選擇 **「儲存位置」** (預設為專案下的 `output` 資料夾)。
* 點擊 **「開始分離人聲」**。
* 完成後，視窗下方會顯示 `✅ 分離運算完成`，檔案會自動整理至輸出資料夾。



### 方法二：使用純腳本模式 (Script Mode)

如果你想透過程式碼批量處理，或不需要介面，可以使用 `separate_audio.py`。

1. 開啟 `separate_audio.py` 修改設定：
```python
INPUT_FILE = "data/test.mp3"  # 修改為你的檔案路徑
OUTPUT_FOLDER = "output"      # 修改輸出位置

```


2. 執行腳本：
```bash
python separate_audio.py

```



---

## 📂 輸出檔案結構

程式會自動將 Demucs 的深層目錄拉平，方便取用。處理後的資料夾結構如下：

```text
output/
└── [檔名]/
    ├── vocals.wav      (人聲)
    └── no_vocals.wav   (伴奏/背景音樂)

```

---

## ❓ 常見問題排查 (Troubleshooting)

**Q: 執行時出現 `RuntimeError: No audio backend is available**`

* **A:** 這是因為缺少 FFmpeg。請執行 `conda install -c conda-forge ffmpeg`。

**Q: 出現 `ImportError: TorchCodec is required**`

* **A:** Torchaudio 版本太新 (2.6.x)。請參照安裝指南第 4 步，將其降級至 2.5.1。

**Q: 出現 `RuntimeError: Couldn't find appropriate backend**`

* **A:** 缺少 Python 的音訊處理後端。請執行 `pip install soundfile`。

**Q: 程式執行很久沒有反應？**

* **A:** 第一次執行時，Demucs 需要下載模型權重 (約數百 MB)，請耐心等候。或是檢查終端機是否有報錯訊息。