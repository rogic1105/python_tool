# Python Tools Collection

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Mac%20%7C%20Windows%20%7C%20Linux-lightgray)]()

各種實用 Python 自動化工具集合，具備統一的 CLI 與 Tab 分頁 GUI 介面，支援 Mac / Windows / Linux。

## 快速開始

```bash
git clone https://github.com/rogic1105/python_tool.git
cd python_tool

# 列出所有可用工具
python run.py

# 啟動圖形介面
python ui.py
```

## 工具列表

### 影音工具 (av)

| 工具 | CLI 名稱 | 說明 | 主要依賴 |
|---|---|---|---|
| Whisper 語音轉錄 | `whisper` | 語音轉文字 + 語者分離，輸出 SRT/TXT | faster-whisper, resemblyzer |
| MP4 轉 MP3 | `mp4_to_mp3` | 批次影片轉 320k MP3 | ffmpeg |
| 影片轉 H.264 | `video_to_h264` | 自動選最佳加速（Mac/CUDA/CPU） | ffmpeg |
| 人聲去除 | `audio_dehuman` | Demucs 分離人聲與背景音 | demucs |
| 取得首尾幀 | `get_frames` | 擷取影片第一幀與最後一幀為 PNG | ffmpeg |

### 占卜工具 (divination)

| 工具 | CLI 名稱 | 說明 | 主要依賴 |
|---|---|---|---|
| 水晶路徑動畫 | `crystal_path` | 六邊形水晶球彩虹軌跡動畫，輸出 MP4 | matplotlib, ffmpeg |

### 資料整理 (data)

| 工具 | CLI 名稱 | 說明 | 主要依賴 |
|---|---|---|---|
| 發票湊數小幫手 | `invoice_helper` | 子集合加總（DP），找最接近目標的金額組合 | numpy |

## 使用方式

### CLI

```bash
# 查看工具說明
python run.py whisper --help

# Whisper 語音轉錄
python run.py whisper audio.mp3 --language zh --speakers 2 --output ./result

# MP4 批次轉 MP3
python run.py mp4_to_mp3 --src ./videos --out ./mp3s

# 影片轉 H.264（自動偵測最佳 codec）
python run.py video_to_h264 video.mkv

# 人聲去除
python run.py audio_dehuman song.mp3 --output ./separated

# 擷取首尾幀
python run.py get_frames video.mp4

# 發票湊數
python run.py invoice_helper --file price.txt

# 水晶路徑動畫
python run.py crystal_path --output ./output
```

### GUI

```bash
python ui.py
```

介面為 Tab 分頁設計，每個類別對應一個分頁，左側選擇工具，右側顯示操作面板。

## 專案結構

```
python_tool/
├── run.py              # 統一 CLI 入口
├── ui.py               # 統一 GUI 入口（Tab 分頁）
├── CLAUDE.md           # Claude AI 開發指引
├── core/               # 框架核心
│   ├── base_tool.py    # BaseTool 抽象基類
│   ├── registry.py     # 工具自動掃描與註冊
│   └── utils.py        # 共用工具（FFmpeg 偵測、平台判斷）
└── tools/              # 所有工具
    ├── av/             # 影音工具
    ├── divination/     # 占卜工具
    └── data/           # 資料整理工具
```

## 新增工具

只需在 `tools/<類別>/` 下建立資料夾，並新增繼承 `BaseTool` 的 `tool.py`，`run.py` 和 `ui.py` 會**自動偵測**，不需修改任何現有檔案。詳見 [CLAUDE.md](./CLAUDE.md)。

## 安裝依賴

由於各工具依賴差異大，建議按需安裝。以 whisper 為例：

```bash
pip install faster-whisper resemblyzer scikit-learn librosa soundfile tqdm
```

FFmpeg 為多數影音工具必備：
```bash
# Mac
brew install ffmpeg

# Windows
# https://ffmpeg.org/download.html
```

## 授權

MIT License — 詳見 [LICENSE](./LICENSE)

---

*Created by [rogic1105](https://github.com/rogic1105)*
