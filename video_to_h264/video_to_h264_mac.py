#!/usr/bin/env python3
"""Converts video to H.264 using Apple Silicon hardware acceleration.

This script uses the 'h264_videotoolbox' codec optimized for Mac M1/M2/M3 chips.
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
        output_path = input_path.with_stem(f"{input_path.stem}_m3").with_suffix('.mp4')

    return output_path


def convert_video_m3(input_path: str, quality: int = 65) -> None:
    """Converts a video using Mac hardware acceleration (videotoolbox).

    Args:
        input_path: The file path of the source video.
        quality: Video quality value (0-100). Default is 65.
                 Higher is better quality but larger file size.

    Raises:
        subprocess.CalledProcessError: If the ffmpeg command fails.
        FileNotFoundError: If the input file does not exist.
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_file = get_output_path(input_file)

    # Build the ffmpeg command for Apple Silicon
    # -c:v h264_videotoolbox: Use Apple's hardware encoder
    # -q:v: Global quality setting (0-100 for videotoolbox)
    # -c:a copy: Copy audio stream directly
    command = [
        'ffmpeg',
        '-y',
        '-i', str(input_file),
        '-c:v', 'h264_videotoolbox',
        '-q:v', str(quality),
        '-c:a', 'copy',
        str(output_file)
    ]

    logging.info(f"Input:  {input_file}")
    logging.info(f"Output: {output_file}")
    logging.info(f"Command: {' '.join(command)}")

    try:
        subprocess.run(command, check=True)
        logging.info("Conversion completed successfully using M3 acceleration.")
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg conversion failed: {e}")
        # Hint for the user if they are not on a Mac
        logging.warning("Ensure you are running this on a Mac with FFmpeg installed.")
        raise


def main() -> None:
    """Parses arguments and initiates the conversion process."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="使用 Mac M3 加速將影片轉為 H.264 (MP4)。"
    )
    parser.add_argument(
        'input_file',
        nargs='?',
        help="來源影片檔案路徑"
    )
    parser.add_argument(
        '--quality',
        type=int,
        default=65,
        help="品質參數 (0-100)，預設 65。數值越高畫質越好。"
    )

    args = parser.parse_args()

    # User-friendly manual output if no arguments provided
    if args.input_file is None:
        print("========================================================")
        print("  尚未指定影片檔案！(M3 加速版)")
        print("  請使用以下指令執行：")
        print("")
        print("  python video_to_h264_m3.py 你的影片檔名.mkv")
        print("========================================================")
        sys.exit(0)

    try:
        convert_video_m3(args.input_file, args.quality)
    except Exception as e:
        logging.error(f"發生錯誤: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()