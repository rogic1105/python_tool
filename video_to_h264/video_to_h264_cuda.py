#!/usr/bin/env python3
"""Converts video to H.264 using NVIDIA CUDA (NVENC) hardware acceleration.

This script uses the 'h264_nvenc' codec optimized for NVIDIA GPUs.
It adheres to the Google Python Style Guide.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path


def setup_logging() -> None:
    """Configures the logging format."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def get_output_path(input_path: Path) -> Path:
    """Derives the output path based on the input filename.

    Args:
        input_path: The path to the source video file.

    Returns:
        Path: The calculated destination path with .mp4 extension.
    """
    output_path = input_path.with_suffix('.mp4')

    # Avoid overwriting input if it is already mp4
    if output_path.resolve() == input_path.resolve():
        output_path = input_path.with_stem(f"{input_path.stem}_cuda").with_suffix('.mp4')

    return output_path


def convert_video_cuda(input_path: str, cq: int = 19) -> None:
    """Converts a video using NVIDIA hardware acceleration (NVENC).

    Args:
        input_path: The file path of the source video.
        cq: Constant Quality value (1-51). Default is 19.
            Lower is better quality. 19 is roughly equivalent to CRF 18-20.

    Raises:
        subprocess.CalledProcessError: If the ffmpeg command fails.
        FileNotFoundError: If the input file does not exist.
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_file = get_output_path(input_file)

    # Build the ffmpeg command for NVIDIA NVENC
    # -c:v h264_nvenc: Use NVIDIA's hardware encoder
    # -preset p6: High quality preset (p1=fastest, p7=slowest/best). p6 is efficient.
    # -tune hq: Tuning for high quality
    # -rc vbr: Variable Bitrate mode (needed for CQ to work properly)
    # -cq: Constant Quality setting (similar to CRF)
    # -b:v 0: Allow bitrate to fluctuate freely based on CQ
    # -c:a copy: Copy audio stream directly
    command = [
        'ffmpeg',
        '-y',
        '-i', str(input_file),
        '-c:v', 'h264_nvenc',
        '-preset', 'p6',
        '-tune', 'hq',
        '-rc', 'vbr',
        '-cq', str(cq),
        '-b:v', '0',
        '-c:a', 'copy',
        str(output_file)
    ]

    logging.info(f"Input:  {input_file}")
    logging.info(f"Output: {output_file}")
    logging.info(f"Command: {' '.join(command)}")

    try:
        subprocess.run(command, check=True)
        logging.info("Conversion completed successfully using CUDA (NVENC).")
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg conversion failed: {e}")
        logging.warning("Ensure you have an NVIDIA GPU and drivers installed.")
        raise


def main() -> None:
    """Parses arguments and initiates the conversion process."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="使用 NVIDIA CUDA (NVENC) 加速將影片轉為 H.264 (MP4)。"
    )
    parser.add_argument(
        'input_file',
        nargs='?',
        help="來源影片檔案路徑"
    )
    parser.add_argument(
        '--cq',
        type=int,
        default=19,
        help="品質參數 CQ (1-51)，預設 19。數值越低畫質越好。"
    )

    args = parser.parse_args()

    # User-friendly manual output if no arguments provided
    if args.input_file is None:
        print("========================================================")
        print("  尚未指定影片檔案！(CUDA 加速版)")
        print("  請使用以下指令執行：")
        print("")
        print("  python video_to_h264_cuda.py 你的影片檔名.mkv")
        print("========================================================")
        sys.exit(0)

    try:
        convert_video_cuda(args.input_file, args.cq)
    except Exception as e:
        logging.error(f"發生錯誤: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()