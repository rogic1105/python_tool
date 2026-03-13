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
    │   ├── whisper/        # 語音轉錄 + 語者分離（faster-whisper + KMeans）
    │   ├── mp4_to_mp3/     # 影片轉 MP3
    │   ├── video_to_h264/  # 影片轉 H.264（自動選 codec）
    │   ├── audio_dehuman/  # Demucs 人聲去除
    │   └── get_frames/     # 擷取首尾幀
    ├── divination/     # 占卜工具
    │   └── crystal_path/   # 水晶路徑動畫
    ├── data/           # 資料整理工具
    │   └── invoice_helper/ # 發票湊數（子集合加總）
    └── system/         # 系統工具
        └── env_manager/    # conda 環境管理（列出／移除）
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
    "system":     "系統工具",
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

   若工具在不同平台需要不同套件（如 CUDA vs CPU），可覆寫 `_resolve_requirements()`：

   ```python
   def _resolve_requirements(self) -> Path:
       import sys as _sys
       if _sys.platform == "darwin":
           mac_req = _TOOL_DIR / "requirements-mac.txt"
           if mac_req.exists():
               return mac_req
       elif _sys.platform == "win32":
           cuda_req = _TOOL_DIR / "requirements-cuda.txt"
           if cuda_req.exists() and _has_nvidia_gpu():
               return cuda_req
       return _TOOL_DIR / "requirements.txt"
   ```

   requirements 檔案命名慣例：
   - `requirements.txt` — Windows CPU（預設 fallback）
   - `requirements-cuda.txt` — Windows GPU（CUDA）
   - `requirements-mac.txt` — macOS

3. 建立 `runner.py`（**獨立腳本**，不 import 任何 core/ 或 tools/）：

   > **⚠️ Windows 編碼注意**：runner.py 開頭必須用 `reconfigure()`，**不可用** `io.TextIOWrapper` 替換 sys.stdout。
   > 替換 wrapper 會在 GC 時關閉底層 buffer，導致後續 `print()` 全部拋出 `ValueError: I/O operation on closed file`。
   > 此問題僅在 Windows 發生（macOS 預設 UTF-8，不需要這段）。

   ```python
   # runner.py — 在隔離環境中執行，使用 stdout 協定回傳狀態
   import sys, os

   # Windows 編碼修正（macOS 不需要）
   if sys.platform == "win32":
       sys.stdout.reconfigure(encoding="utf-8", errors="replace")
       sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

## 平台隔離規則（跨平台修改守則）

> **Claude Code 必讀指令**：本專案同時在 macOS 與 Windows 上使用。
> 每次修改前，必須先判斷目前所在平台，並嚴格遵守以下規則，**不得因修一個平台而動到另一個平台的邏輯**。

### 修改前必做的平台確認

拿到任何修改需求時，先自問：

1. **這段邏輯是共用的還是平台專屬的？**
   - 共用（`core/`、`tools/` 內無 `sys.platform` 分支）→ 修改後必須兩個平台都能運作
   - 平台專屬（有 `if sys.platform == "win32":` 或 `if sys.platform == "darwin":` 包住）→ 只改對應那段，不碰另一段
2. **有沒有對應平台的 requirements 檔案？** → 只改當前平台的那個（`requirements.txt` / `requirements-cuda.txt` / `requirements-mac.txt`）
3. **有沒有對應平台的啟動腳本？** → `launch.bat` 只在 Windows 改，`launch.sh` 只在 macOS 改

### 硬性禁止事項

- ❌ **禁止**在 Windows 上修改 `if sys.platform == "darwin":` 區塊內的任何程式碼
- ❌ **禁止**在 macOS 上修改 `if sys.platform == "win32":` 區塊內的任何程式碼
- ❌ **禁止**為了修 Windows 問題而刪除或更動 Mac 專屬設定（反之亦然）
  - 例如：`get_best_h264_codec()` 中 `h264_videotoolbox` 的設定，在 Windows 上絕對不可動
  - 例如：`requirements-mac.txt` 的內容，在 Windows 上絕對不可動
- ❌ **禁止**在 `.bat` 檔案中加入中文（會亂碼）
- ❌ **禁止**在 `.sh` 檔案中使用 Windows 路徑或 `%VAR%` 語法

### 正確的平台分支寫法

```python
# ✅ 正確：用 sys.platform 明確分支
if sys.platform == "win32":
    # Windows 專屬邏輯
    ...
elif sys.platform == "darwin":
    # macOS 專屬邏輯
    ...
else:
    # Linux fallback
    ...

# ❌ 錯誤：不分平台直接寫，導致其中一個平台壞掉
sys.stdout = io.TextIOWrapper(...)  # Windows 有 GC bug，Mac 不需要
```

---

## Windows 相容性已知問題與解法

新增 Windows 功能時必須注意，以下是實際踩過的坑：

### 1. subprocess 中文亂碼 / cp950 編碼錯誤（Windows 專屬）

**症狀**：`'cp950' codec can't encode character` 或 log 顯示亂碼。

**原因**：Windows Python 預設 stdout 為 cp950（Big5），中文字元超出範圍就崩潰。macOS 預設 UTF-8，不會發生。

**解法**（兩層都要做）：

```python
# (A) 呼叫端 Popen 加環境變數（呼叫所有 runner.py 時都要加）
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
proc = subprocess.Popen(cmd, ..., encoding="utf-8", errors="replace", env=env)

# (B) runner.py 開頭用 reconfigure()（Windows 專屬，macOS 不需要）
# ⚠️ 絕對不能用 io.TextIOWrapper 替換 sys.stdout！
# 替換後舊的 wrapper 被 GC 時會關掉底層 buffer，導致之後所有 print() 崩潰。
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

### 2. conda 不在 PATH（Windows 專屬）

**症狀**：`conda env list` 找不到命令，環境掃描失敗。

**原因**：Windows 的 conda 只在 Anaconda Prompt 裡有 PATH，直接跑 `python ui.py` 沒有。

**解法**：使用 `core/isolated_tool.py` 的 `_find_conda_exe()`，會掃描常見安裝位置：
`%USERPROFILE%\anaconda3\Scripts\conda.exe` 等。

### 3. conda env list --json 沒有環境名稱（Windows 專屬）

**症狀**：環境列表只顯示路徑，base 環境標成 `anaconda3`。

**原因**：`conda env list --json` 的 `envs` 欄位只有路徑，沒有名稱；且 base 路徑重複出現（大小寫不同）。

**解法**：改用 `conda env list`（文字格式）解析，第一欄就是名稱：

```python
# 使用 _parse_conda_env_list(conda_exe) → [(name, path), ...]
# 在 core/isolated_tool.py 已實作
```

### 4. conda Python 位置與 venv 不同（Windows 專屬）

**症狀**：掃描到 conda 環境但找不到 python.exe，顯示為空。

**原因**：Windows conda 環境的 `python.exe` 直接放在環境**根目錄**，不在 `Scripts\` 下。
Mac conda 放在 `bin/python`（已涵蓋）。

**解法**：`_python_in_dir()` 候選路徑順序：
```python
d / "bin" / "python"       # Mac/Linux venv + conda
d / "Scripts" / "python.exe"  # Windows venv
d / "python.exe"           # Windows conda (根目錄)
```

### 5. matplotlib FFMpegWriter 找不到 ffmpeg（Windows 專屬）

**症狀**：`[WinError 2] 系統找不到指定的檔案`。

**原因**：matplotlib 不會自動查 PATH 以外的位置，Windows 常見安裝路徑未在 PATH。

**解法**：在工具 `core.py` 開頭設定 rcParams：

```python
from core.utils import FFMPEG_CMD
matplotlib.rcParams["animation.ffmpeg_path"] = FFMPEG_CMD
```

### 6. pyenv 路徑差異（Windows 專屬）

**原因**：pyenv-win 安裝在 `~/.pyenv/pyenv-win/versions/`，不是 Mac 的 `~/.pyenv/versions/`。

**解法**：`scan_candidate_envs()` 的 pyenv 掃描已用 `sys.platform == "win32"` 分支處理。

### 7. conda subprocess 污染父程序 stdout（Windows 專屬）

**症狀**：呼叫 `conda env list` 之後，主程式的 `print()` 全部停止輸出或 log 區空白。

**原因**：conda.BAT 透過 cmd.exe 執行，cmd.exe 會操作 console handle，導致父程序的 stdout 被破壞。macOS 的 conda 是 shell script，不會發生此問題。

**解法**：**完全不呼叫 conda subprocess**。改用 filesystem 直接掃描：
- 從 conda.exe 路徑推算 conda root（`conda.exe` 所在的 `Scripts/` 的上層目錄）
- 讀取 conda root 的 `envs/` 子目錄列出所有環境
- 補充讀取 `~/.conda/environments.txt`（跨 root 安裝的環境）

已實作於 `core/isolated_tool.py` 的 `_scan_conda_envs_fs()`；
`_parse_conda_env_list()` 在 Windows 自動呼叫 fs 版本，macOS/Linux 維持原本的 subprocess 版本。

### 8. faster-whisper `del model` 在 CUDA 上卡死（Windows 專屬）

**症狀**：長音訊（>30 分鐘）轉錄完成後，日誌停在「釋放模型記憶體...」，後續對齊和寫檔步驟完全不執行。

**原因**：CTranslate2 在 Windows CUDA 環境中，顯式 `del model` 有時觸發 CUDA context cleanup deadlock。

**解法**：**不要顯式 `del model`**，直接讓 subprocess 退出時由 OS 自動回收 GPU 記憶體：

```python
# ❌ 會卡死
del model

# ✅ 正確：不需要 del，subprocess 結束 OS 自動清理
# （直接進行下一步）
```

### 9. faster-whisper VAD 過濾掉歌聲（通用）

**症狀**：轉錄歌曲時只輸出前 1 分鐘，後面全部漏掉。

**原因**：Silero VAD 預設 `threshold=0.5`，歌聲信心分數約 0.1–0.3，被全部過濾。

**解法**：降低 VAD threshold，並增加 padding：

```python
segs, info = model.transcribe(
    wav_path, language=lang, beam_size=5,
    vad_filter=True,
    vad_parameters={
        "threshold": 0.05,           # 預設 0.5 太嚴，歌聲需要 0.05
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 800,
    },
    condition_on_previous_text=False,  # False 防止幻覺傳播
    initial_prompt="以下是普通話語音。",   # 中文提示防止混入英文
)
```

**注意**：`vad_filter=False` 雖然覆蓋率最高，但會對純音樂段產生大量幻覺輸出，不建議使用。

### 10. .bat 檔案 for 迴圈引號問題（Windows 專屬）

**症狀**：`call "%VAR%"` 出現「檔案名稱語法錯誤」。

**原因**：`for %%C in ("帶引號路徑")` 會讓變數本身包含引號，`call "%VAR%"` 變成雙重引號。

**解法**：for 迴圈內路徑**不加引號**，只在 `if exist "%%C"` 和 `call "%VAR%"` 加：

```bat
for %%C in (
    %USERPROFILE%\anaconda3\Scripts\activate.bat
) do (
    if exist "%%C" set CONDA_ACTIVATE=%%C
)
call "%CONDA_ACTIVATE%" base
```

---

## 核心設計原則

- **業務邏輯**放在 `core.py` 或 `src/`，不混入 `tool.py`
- **`tool.py`** 只負責：定義 metadata、CLI 參數、呼叫核心邏輯、回傳 UI panel
- **GUI panel** 繼承 `ttk.Frame`，不使用 `tk.Tk`（已是子視窗）
- **跨平台路徑**使用 `pathlib.Path`，FFmpeg 路徑透過 `core.utils.FFMPEG_CMD` 取得
- **subprocess 編碼**：所有 `Popen` 必須加 `encoding="utf-8", errors="replace"` + `env["PYTHONIOENCODING"]="utf-8"`
- **matplotlib 工具**：加 `matplotlib.use("Agg")` 避免彈出視窗干擾 tkinter；Windows 需額外設定 `rcParams["animation.ffmpeg_path"]`
- **執行結果**：顯示在 log 區，不用 `messagebox`
- **開啟資料夾/檔案**：使用 `core.utils.open_folder(path)`，跨平台（Windows: `os.startfile`，macOS: `open`，Linux: `xdg-open`）；若 path 是檔案則自動開啟其所在目錄；每個輸入/輸出欄位旁都應提供「開啟」按鈕

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

