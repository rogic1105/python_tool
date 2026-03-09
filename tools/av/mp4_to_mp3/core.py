import subprocess
from pathlib import Path
from core.utils import FFMPEG_CMD


SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}


def convert_to_mp3(src_dir: str = "src", out_dir: str = "out", log_cb=print) -> dict:
    src_path = Path(src_dir)
    out_path = Path(out_dir)
    src_path.mkdir(parents=True, exist_ok=True)
    out_path.mkdir(parents=True, exist_ok=True)

    converted, skipped = 0, 0

    for video_file in src_path.iterdir():
        if not video_file.is_file() or video_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        mp3_file = out_path / (video_file.stem + ".mp3")
        if mp3_file.exists():
            log_cb(f"[略過] {mp3_file.name} 已存在")
            skipped += 1
            continue
        log_cb(f"[轉換] {video_file.name} -> {mp3_file.name}")
        cmd = [FFMPEG_CMD, "-i", str(video_file), "-vn", "-b:a", "320k", str(mp3_file)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log_cb(f"[完成] {mp3_file.name}")
            converted += 1
        except subprocess.CalledProcessError as e:
            log_cb(f"[錯誤] {video_file.name} 轉換失敗: {e}")
        except FileNotFoundError:
            log_cb("[錯誤] 找不到 FFmpeg，請確認已安裝並加入 PATH")
            return {"converted": converted, "skipped": skipped}

    return {"converted": converted, "skipped": skipped}
