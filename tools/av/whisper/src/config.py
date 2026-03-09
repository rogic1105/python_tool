import os
import platform

SYSTEM = platform.system()

DEFAULT_OUTPUT_DIR = os.path.join(os.getcwd(), "output")

MODEL_CACHE_DIR = None

SR = 16000
WIN_SEC = 1.5
HOP_SEC = 0.75
ENERGY_THRESH = 0.01


def setup_env():
    if SYSTEM == "Windows":
        os.environ["LOKY_MAX_CPU_COUNT"] = "4"
    elif SYSTEM == "Darwin":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
