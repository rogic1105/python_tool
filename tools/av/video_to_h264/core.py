import subprocess
from pathlib import Path
from core.utils import FFMPEG_CMD, get_best_h264_codec


def get_output_path(input_path: Path) -> Path:
    output_path = input_path.with_suffix(".mp4")
    if output_path.resolve() == input_path.resolve():
        output_path = input_path.with_stem(f"{input_path.stem}_h264").with_suffix(".mp4")
    return output_path


def convert_to_h264(input_path: str, quality: int = None, log_cb=print) -> Path:
    """Convert video to H.264. Auto-selects best codec for the platform."""
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"找不到檔案: {input_path}")

    output_file = get_output_path(input_file)
    codec, extra_args = get_best_h264_codec()

    # Override quality if provided
    if quality is not None:
        if codec == "h264_videotoolbox":
            extra_args = ["-q:v", str(quality)]
        elif codec == "libx264":
            extra_args = ["-preset", "slow", "-crf", str(quality)]

    cmd = [FFMPEG_CMD, "-y", "-i", str(input_file), "-c:v", codec] + extra_args + ["-c:a", "copy", str(output_file)]
    log_cb(f"[轉換] {input_file.name} -> {output_file.name}  (codec: {codec})")

    try:
        subprocess.run(cmd, check=True)
        log_cb(f"[完成] {output_file.name}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg 轉換失敗: {e}")

    return output_file
