
# Python Tools Collection (Python 小工具集合)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)

這是一個存放各種實用 Python 自動化腳本與應用程式的倉庫。
專案內容包含從簡單的演算法計算到結合 AI 模型的複雜應用，未來將持續新增更多實用工具以解決生活或工作中的各種問題。

This repository collects various practical Python scripts and tools. More tools will be added over time.

## 🧰 工具列表 (Tools List)

目前收錄的工具如下，點擊連結可查看詳細使用說明與安裝方式：

| 工具名稱 | 資料夾 | 簡介 | 關鍵技術 / 應用 |
| :--- | :--- | :--- | :--- |
| **發票湊數小幫手**<br>(Invoice Helper) | [`/invoice_helper`](./invoice_helper/readme.md) | 解決「子集合加總問題」。協助從一堆金額中找出總和最接近目標金額的組合。 | • Dynamic Programming (DP)<br>• 帳務處理、發票報銷 |
| **語音轉錄與語者分離**<br>(Whisper Diarization) | [`/audio_whisper`](./audio_whisper/readme.md) | 本機端的語音轉文字工具。除產生逐字稿外，還能自動區分不同的說話者 (Speaker A, Speaker B)。 | • OpenAI Faster-Whisper<br>• Resemblyzer (聲紋分析)<br>• 會議記錄、字幕製作 |

## 🚀 快速開始 (Getting Started)

由於每個工具所需的依賴套件 (Dependencies) 差異較大（例如 `invoice_helper` 只需要 numpy，而 `audio_whisper` 需要 PyTorch 等深度學習庫），建議依照以下步驟使用：

1. **複製專案到本地**
   ```bash
   git clone [https://github.com/rogic1105/python_tool.git](https://github.com/rogic1105/python_tool.git)
   cd python_tool

```

2. **進入感興趣的工具目錄**
```bash
cd invoice_helper
# 或
cd audio_whisper

```


3. **查看該目錄下的 README 並安裝對應依賴**
每個工具資料夾內皆有獨立的 `readme.md` 與需求說明。

## 📂 專案結構 (Structure)

```text
python_tool/
├── audio_whisper/     # [AI] 語音轉錄與語者分離工具 (含 GUI/CLI)
├── invoice_helper/    # [Algo] 發票金額湊數工具 (含 GUI/CLI)
├── .gitignore
├── LICENSE
└── README.md          # 本檔案

```

## 📝 授權 (License)

本專案採用 **MIT License** 開源授權，詳情請見 [LICENSE](https://www.google.com/search?q=./LICENSE) 文件。
歡迎自由使用、修改與分發，但請保留原作者版權聲明。

---

*Created by [rogic1105*](https://www.google.com/search?q=https://github.com/rogic1105)

