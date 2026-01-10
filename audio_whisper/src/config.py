import os
import platform

# 環境偵測
SYSTEM = platform.system()

# 路徑設定
CWD = os.getcwd()
DEFAULT_OUTPUT_DIR = os.path.join(CWD, "data_out")

# 修改：設為 None 代表使用系統預設 (HuggingFace Cache)
MODEL_CACHE_DIR = None 

# 音訊參數
SR = 16000
WIN_SEC = 1.5
HOP_SEC = 0.75
ENERGY_THRESH = 0.01

# 環境變數設置
def setup_env():
    if SYSTEM == "Windows":
        os.environ["LOKY_MAX_CPU_COUNT"] = "4"
    elif SYSTEM == "Darwin":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")