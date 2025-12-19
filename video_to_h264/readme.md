# FFmpeg H.264 影片轉檔工具

這是一個 Python 腳本工具包，用於呼叫 FFmpeg 將各種格式的影片轉換為高品質的 H.264 (MP4) 格式。

主要特色：

* **不縮放**：保持原始解析度。
* **高品質**：預設參數皆設定為「視覺無損」(Visually Lossless)。
* **音訊保留**：使用 Copy 模式，不對音訊進行二次編碼，保留原始音質。
* **自動命名**：自動根據輸入檔名產生輸出檔名，避免覆蓋原始檔案。

## 包含的腳本

本專案包含三個針對不同硬體環境優化的腳本：

* **video_to_h264_general.py**
* **適用環境**：所有安裝了 FFmpeg 的電腦（Windows, Linux, macOS）。
* **編碼器**：`libx264` (CPU 運算)。
* **特點**：相容性最高，壓縮率最好，但速度較慢。


* **video_to_h264_mac.py**
* **適用環境**：Apple Silicon 電腦 (M1, M2, M3)。
* **編碼器**：`h264_videotoolbox`。
* **特點**：利用 Media Engine 硬體加速，轉檔速度極快。


* **video_to_h264_cuda.py**
* **適用環境**：配備 NVIDIA 顯示卡的電腦。
* **編碼器**：`h264_nvenc`。
* **特點**：利用 NVIDIA GPU 加速，大幅降低 CPU 負載。



## 先決條件 (Prerequisites)

在使用此工具前，請確保您的系統已滿足以下條件：

1. **Python 3.6+**：已安裝並加入環境變數。
2. **FFmpeg**：
* 必須安裝並加入系統 PATH 環境變數。
* 若使用 CUDA 版本，FFmpeg 必須支援 NVENC。


3. **驅動程式** (僅 CUDA 版)：需安裝最新的 NVIDIA 驅動程式。

## 使用方式 (Usage)

### 1. 通用版 (General CPU)

最標準的轉換方式。

```bash
python video_to_h264_general.py input_video.mkv

```

**可選參數：**

* `--crf`：設定畫質 (0-51)。預設值為 **18**。數值越低畫質越好，檔案越大。

### 2. Mac M3 加速版 (Apple Silicon)

適用於 macOS 使用者。

```bash
python video_to_h264_mac.py input_video.mkv

```

**可選參數：**

* `--quality`：設定畫質 (0-100)。預設值為 **65**。數值越高畫質越好。

### 3. NVIDIA CUDA 加速版

適用於 Windows/Linux 且擁有 NVIDIA 顯卡的使用者。

```bash
python video_to_h264_cuda.py input_video.mkv

```

**可選參數：**

* `--cq`：設定固定品質參數 (1-51)。預設值為 **19**。數值越低畫質越好。

## Windows 拖曳執行 (選用)

若不想使用命令列，可以建立一個 `.bat` 批次檔來實現「拖曳轉檔」。

1. 新增一個文字檔，命名為 `拖曳影片到此.bat`。
2. 將下方內容貼上並儲存（請將 `your_script_name.py` 替換為你想使用的 Python 檔名）：

```batch
@echo off
if "%~1"=="" (
    echo 請將影片檔案拖曳到這個圖示上以開始轉檔。
    pause
    exit /b
)

:: 在此修改你要使用的腳本名稱，例如 video_to_h264_cuda.py
python video_to_h264_general.py "%~1"

echo.
echo 轉檔完成！
pause

```

3. 現在，將影片檔案拖曳到這個 `.bat` 檔案上即可自動開始轉檔。

## 參數對照表

不同編碼器使用的畫質參數標準不同，以下為預設值的對照：

* **libx264 (CPU)**: 使用 `CRF`，預設 **18** (視覺無損)。
* **Videotoolbox (Mac)**: 使用 `Global Quality`，預設 **65**。
* **NVENC (CUDA)**: 使用 `CQ`，預設 **19**。

## 故障排除

* **找不到檔案 (FileNotFoundError)**：請確認輸入的路徑正確，且路徑中不包含特殊字元。
* **FFmpeg 錯誤**：
* 通用版：請確認終端機輸入 `ffmpeg -version` 能看到資訊。
* CUDA 版：請輸入 `ffmpeg -encoders | findstr nvenc` 確認您的 FFmpeg 支援 NVIDIA 編碼。
* Mac 版：請確認您是在 macOS 環境下執行。