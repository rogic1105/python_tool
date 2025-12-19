#!/usr/bin/env python3
"""Converts video to H.264 format using ffmpeg without scaling.

This script adheres to the Google Python Style Guide. It automatically
derives the output filename from the input filename.
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

    The default behavior is to change the extension to .mp4.
    If the input is already .mp4, it appends '_h264' to the stem to
    prevent overwriting the source file during ffmpeg processing.

    Args:
        input_path: The path to the source video file.

    Returns:
        Path: The calculated destination path.
    """
    # Default to .mp4 as it is the standard container for H.264
    output_path = input_path.with_suffix('.mp4')

    # Avoid input/output collision if the input is already .mp4
    if output_path.resolve() == input_path.resolve():
        output_path = input_path.with_stem(f"{input_path.stem}_h264").with_suffix('.mp4')

    return output_path


def convert_video_to_h264(input_path: str, crf: int = 18) -> None:
    """Converts a video file to H.264 format using ffmpeg.

    Args:
        input_path: The file path of the source video.
        crf: Constant Rate Factor (0-51). Default is 18.

    Raises:
        subprocess.CalledProcessError: If the ffmpeg command fails.
        FileNotFoundError: If the input file does not exist.
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_file = get_output_path(input_file)

    # Build the ffmpeg command
    # -i: Input file
    # -c:v libx264: Use H.264 video codec
    # -preset slow: Better compression efficiency
    # -crf: Quality setting (18 is visually lossless)
    # -c:a copy: Copy audio stream directly
    command = [
        'ffmpeg',
        '-y',  # Overwrite output file without asking
        '-i', str(input_file),
        '-c:v', 'libx264',
        '-preset', 'slow',
        '-crf', str(crf),
        '-c:a', 'copy',
        str(output_file)
    ]

    logging.info(f"Input:  {input_file}")
    logging.info(f"Output: {output_file}")
    logging.info(f"Command: {' '.join(command)}")

    try:
        subprocess.run(command, check=True)
        logging.info("Conversion completed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg conversion failed: {e}")
        raise


def main() -> None:
    """Parses arguments and initiates the conversion process."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="將影片轉換為 H.264 (MP4) 並維持原畫質。"
    )
    parser.add_argument(
        'input_file',
        nargs='?',  # 允許不輸入，這樣我們才能手動檢查並印出教學
        help="來源影片檔案路徑"
    )
    parser.add_argument(
        '--crf',
        type=int,
        default=18,
        help="畫質參數 (CRF 0-51)，預設為 18 (視覺無損)。"
    )

    args = parser.parse_args()

    # 如果沒有輸入檔案，印出中文教學並離開
    if args.input_file is None:
        print("========================================================")
        print("  尚未指定影片檔案！")
        print("  請使用以下指令執行：")
        print("")
        print("  python video_to_h264.py 你的影片檔名.mkv")
        print("========================================================")
        sys.exit(0)

    try:
        convert_video_to_h264(args.input_file, args.crf)
    except Exception as e:
        logging.error(f"發生錯誤: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()