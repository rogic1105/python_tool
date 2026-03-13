import os
import platform

SYSTEM = platform.system()

DEFAULT_OUTPUT_DIR = os.path.join(os.getcwd(), "output")


def setup_env():
    if SYSTEM == "Windows":
        os.environ["LOKY_MAX_CPU_COUNT"] = "4"
    elif SYSTEM == "Darwin":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
