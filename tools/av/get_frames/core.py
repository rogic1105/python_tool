import subprocess
import json
import os
from pathlib import Path
from core.utils import FFMPEG_CMD


def get_first_last_frames(video_path: str, output_prefix: str = None, log_cb=print) -> bool:
    if not os.path.exists(video_path):
        log_cb(f"[錯誤] 找不到檔案: {video_path}")
        return False

    if output_prefix is None:
        base = os.path.splitext(video_path)[0]
        first_out = f"{base}_first_frame.png"
        last_out = f"{base}_last_frame.png"
    else:
        first_out = f"{output_prefix}_first_frame.png"
        last_out = f"{output_prefix}_last_frame.png"

    ffprobe = FFMPEG_CMD.replace("ffmpeg", "ffprobe")

    try:
        probe_cmd = [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-count_packets", "-show_entries", "stream=nb_read_packets,duration",
            "-of", "json", video_path,
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(result.stdout)
        if not probe_data.get("streams"):
            log_cb("[錯誤] 找不到視訊串流")
            return False

        first_cmd = [
            FFMPEG_CMD, "-i", video_path,
            "-vf", "select=eq(n\\,0)", "-vframes", "1", "-y", first_out,
        ]
        subprocess.run(first_cmd, capture_output=True, check=True)
        log_cb(f"[完成] 第一幀: {first_out}")

        last_cmd = [
            FFMPEG_CMD, "-sseof", "-1", "-i", video_path,
            "-update", "1", "-frames:v", "1", "-y", last_out,
        ]
        subprocess.run(last_cmd, capture_output=True, check=True)
        log_cb(f"[完成] 最後幀: {last_out}")
        return True

    except subprocess.CalledProcessError as e:
        log_cb(f"[錯誤] ffmpeg/ffprobe 失敗: {e}")
        return False
    except Exception as e:
        log_cb(f"[錯誤] {e}")
        return False
