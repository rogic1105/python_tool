import os
import subprocess
from pathlib import Path

def convert_video_to_audio(src_dir="src", out_dir="out"):
    src_path = Path(src_dir)
    out_path = Path(out_dir)

    # 確保資料夾存在，如果不存在則建立
    src_path.mkdir(parents=True, exist_ok=True)
    out_path.mkdir(parents=True, exist_ok=True)

    # 支援的影片格式
    supported_extensions = {".mp4", ".mov"}

    # 計算轉換數量
    converted_count = 0
    skipped_count = 0

    print(f"開始掃描 {src_dir} 資料夾...")

    # 尋找所有影片檔案
    for video_file in src_path.iterdir():
        if video_file.is_file() and video_file.suffix.lower() in supported_extensions:
            # 建立輸出的 mp3 檔案路徑
            mp3_filename = video_file.stem + ".mp3"
            mp3_file = out_path / mp3_filename

            # 如果 mp3 檔案已經存在，則跳過
            if mp3_file.exists():
                print(f"[略過] {mp3_filename} 已經存在於 {out_dir} 中。")
                skipped_count += 1
                continue

            print(f"[轉換中] {video_file.name} -> {mp3_filename}...")
            
            # 使用 ffmpeg 進行轉換
            command = [
                "ffmpeg",
                "-i", str(video_file),
                "-vn",              # 停用影片流，只保留音訊
                "-b:a", "320k",     # 音訊品質：320k 是 MP3 的最高音質上限
                str(mp3_file)
            ]
            
            try:
                # 執行指令，不顯示 ffmpeg 的冗長輸出
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"[成功] 轉換完成：{mp3_filename}")
                converted_count += 1
            except subprocess.CalledProcessError as e:
                print(f"[錯誤] 轉換 {video_file.name} 失敗：{e}")
            except FileNotFoundError:
                print("[錯誤] 找不到 FFmpeg 執行檔！請確保已安裝 FFmpeg 並已加入系統環境變數 PATH 中。")
                return

    print("="*30)
    print(f"處理完成！共轉換了 {converted_count} 個檔案，略過了 {skipped_count} 個檔案。")

if __name__ == "__main__":
    convert_video_to_audio()
