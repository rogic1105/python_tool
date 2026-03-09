# CLAUDE.md — Python Tools 專案說明

## 專案架構

```
python_tool/
├── run.py              # 統一 CLI 入口：python run.py <tool> [args]
├── ui.py               # 統一 GUI 入口：python ui.py
├── core/               # 框架核心（不含業務邏輯）
│   ├── base_tool.py        # BaseTool 抽象基類
│   ├── registry.py         # 自動掃描工具（discover_tools）
│   ├── utils.py            # 共用工具（ffmpeg、平台偵測、load_pref/save_pref）
│   ├── isolated_tool.py    # IsolatedTool 基類（隔離 venv 執行）
│   └── isolated_panel.py   # IsolatedPanel GUI（VSCode 風格環境選擇器）
└── tools/              # 所有工具（按類別分層）
    ├── av/             # 影音工具
    │   ├── whisper/        # 語音轉錄 + 語者分離
    │   ├── mp4_to_mp3/     # 影片轉 MP3
    │   ├── video_to_h264/  # 影片轉 H.264（自動選 codec）
    │   ├── audio_dehuman/  # Demucs 人聲去除
    │   └── get_frames/     # 擷取首尾幀
    ├── divination/     # 占卜工具
    │   └── crystal_path/   # 水晶路徑動畫
    └── data/           # 資料整理工具
        └── invoice_helper/ # 發票湊數（子集合加總）
```

持久化設定存放位置：
```
.venvs/
├── env_config.json     # 各工具已選擇的 Python 路徑 { "venv_name": "/path/to/python" }
└── ui_prefs.json       # UI 使用者偏好 { "tool.output_dir": "/path" }
```

---

## 新增工具流程

1. 在對應類別目錄下建立新資料夾，例如 `tools/av/my_tool/`
2. 建立 `__init__.py`（空白）
3. 建立 `tool.py`，繼承 `BaseTool`：

```python
from core.base_tool import BaseTool
import argparse, tkinter as tk

class MyTool(BaseTool):
    name = "my_tool"           # CLI 名稱（唯一）
    display_name = "我的工具"   # UI 顯示名稱
    category = "av"            # "av" | "divination" | "data"
    description = "一行說明"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("input", help="輸入檔案")

    def run_cli(self, args) -> None:
        print(f"處理: {args.input}")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        # 選擇性覆寫；若不覆寫，會顯示預設的文字說明面板
        from .gui_panel import MyPanel
        return MyPanel(parent)
```

4. 完成，`run.py` 和 `ui.py` 會自動偵測並載入。**不需要修改任何其他檔案。**

---

## 新增工具類別

在 `core/registry.py` 的 `CATEGORY_LABELS` 字典新增：
```python
CATEGORY_LABELS = {
    "av":         "影音工具",
    "divination": "占卜工具",
    "data":       "資料整理",
    "new_cat":    "新類別名稱",   # 新增這行
}
```
並在 `tools/` 下建立對應目錄和 `__init__.py`。

---

## 解決依賴衝突：IsolatedTool

當工具的依賴套件（PyTorch、TensorFlow 等）互相衝突時，使用 `IsolatedTool`：

```
主程式 (run.py / ui.py) → 輕量 base env（只需 tkinter）
    ├── subprocess → .venvs/whisper/   (PyTorch + faster-whisper)
    ├── subprocess → .venvs/demucs/    (demucs)
    └── 直接執行  → mp4_to_mp3, get_frames, invoice_helper（無衝突依賴）
```

### 新增有隔離需求的工具

1. `tool.py` 繼承 `IsolatedTool`（而非 `BaseTool`）：

```python
from core.isolated_tool import IsolatedTool

class MyTool(IsolatedTool):
    name = "my_tool"
    display_name = "我的工具"
    category = "av"
    description = "一行說明"

    venv_name = "my_tool"          # .venvs/my_tool/ 或 conda env 名稱基礎
    requirements_file = "requirements.txt"
    check_imports = ["my_package"]  # 用來驗證環境是否齊全

    def _runner_path(self) -> Path:
        return Path(__file__).parent / "runner.py"

    def _runner_args(self, args) -> list:
        return [args.input, "--output", args.output]

    def _build_panel(self, parent) -> tk.Widget:
        return MyPanel(parent, self)
```

2. 建立 `requirements.txt`（套件清單）

3. 建立 `runner.py`（**獨立腳本**，不 import 任何 core/ 或 tools/）：

```python
# runner.py — 在隔離環境中執行，使用 stdout 協定回傳狀態
import sys, os

# 輸出協定（IsolatedTool / GUI 自動解析）：
print("LOG:開始處理...", flush=True)
print("PROGRESS:1,50,", flush=True)   # stage, 0-100, msg
print("TEXT:轉錄的文字", flush=True)
print("DONE:/path/to/output", flush=True)
print("ERROR:錯誤訊息", flush=True)
```

4. GUI panel 中執行時，使用 **`self.tool.active_python`**（而非 `venv_python`）：

```python
cmd = [self.tool.active_python, str(RUNNER), input_path, "--output", out_dir]
proc = subprocess.Popen(
    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, encoding="utf-8", errors="replace", bufsize=1,
)
```

> **注意**：`venv_python` 永遠指向 `.venvs/<name>/bin/python`（managed venv 固定路徑）。
> `active_python` 才會讀取 `env_config.json`，回傳使用者實際選擇的環境（可能是 conda env）。

---

## IsolatedPanel — 環境選擇器（VSCode 風格）

`IsolatedTool` 的 `get_ui_panel()` 會自動回傳 `IsolatedPanel`，流程如下：

```
打開工具
  ├─ is_ready=True  → 直接顯示工具面板（頂部顯示當前環境路徑）
  └─ is_ready=False → 環境選擇器
        1. 背景快速掃描所有 Python 環境（只找執行檔，不驗套件）
           掃描來源：目前環境、conda envs、pyenv、.venvs/、本地 venv
        2. 列表邊掃描邊填入
        3. 使用者點選一個環境 → 背景驗證該環境的 check_imports
           ✓ 所需套件齊全（綠）  ✗ 缺少套件（紅）
        4. 「使用此環境」→ 存入 env_config.json，切換至工具面板
        5. 「新建 venv 環境」→ 建立 .venvs/<name>/ + pip install
        6. 「新建 conda 環境」→ 彈出 dialog 設定名稱與 Python 版本
              conda create -n <name> python=<ver> -y
              conda run -n <name> pip install -r requirements.txt
```

頂部「更換環境」按鈕 → 清除 env_config.json 中的紀錄，回到選擇器。

---

## UI 偏好持久化

使用 `core/utils.py` 的 `load_pref` / `save_pref`，資料存在 `.venvs/ui_prefs.json`：

```python
from core.utils import load_pref, save_pref

# 讀取（附帶預設值）
default_out = load_pref("my_tool.output_dir", os.getcwd())

# 使用者選目錄後儲存
def _browse_output(self):
    p = filedialog.askdirectory()
    if p:
        self.output_var.set(p)
        save_pref("my_tool.output_dir", p)
```

Key 命名慣例：`"<tool_name>.<setting>"`

---

## 核心設計原則

- **業務邏輯**放在 `core.py` 或 `src/`，不混入 `tool.py`
- **`tool.py`** 只負責：定義 metadata、CLI 參數、呼叫核心邏輯、回傳 UI panel
- **GUI panel** 繼承 `ttk.Frame`，不使用 `tk.Tk`（已是子視窗）
- **跨平台路徑**使用 `pathlib.Path`，FFmpeg 路徑透過 `core.utils.FFMPEG_CMD` 取得
- **subprocess 編碼**：所有 `Popen` 必須加 `encoding="utf-8", errors="replace"`，否則非 ASCII 路徑會導致解碼失敗
- **matplotlib 工具**：加 `matplotlib.use("Agg")` 避免彈出視窗干擾 tkinter
- **執行結果**：顯示在 log 區，不用 `messagebox`

---

## 常用指令

```bash
# 列出所有工具
python run.py

# 執行特定工具
python run.py whisper audio.mp3 --language zh --speakers 2
python run.py mp4_to_mp3 --src ./videos --out ./mp3s
python run.py video_to_h264 video.mkv
python run.py invoice_helper --file price.txt

# 啟動 GUI
python ui.py
```

