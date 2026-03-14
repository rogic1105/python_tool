"""
Audio Visualizer runner — runs in isolated venv.

Usage:
    python runner.py <audio_path> <output_path>

Stdout protocol:
    LOG:<msg>
    PROGRESS:<stage>,<0-100>,<msg>
    DONE:<output_path>
    ERROR:<msg>
"""
import sys
import os


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 3:
        print("ERROR:用法：runner.py <audio_path> <output_path>", flush=True)
        sys.exit(1)

    audio_path  = sys.argv[1]
    output_path = sys.argv[2]

    try:
        import numpy as np
        import librosa
        import cv2
        from moviepy import VideoClip, AudioFileClip
    except ImportError as e:
        print(f"ERROR:缺少套件：{e}", flush=True)
        sys.exit(1)

    def get_rainbow_color(idx, total):
        hue = int((idx / (total - 1)) * 140)
        color_hsv = np.uint8([[[hue, 255, 255]]])
        color_bgr = cv2.cvtColor(color_hsv, cv2.COLOR_HSV2BGR)[0][0]
        return (int(color_bgr[0]), int(color_bgr[1]), int(color_bgr[2]))

    def make_video(audio_path, output_path):
        print("LOG:載入音訊並擷取頻譜特徵...", flush=True)
        print("PROGRESS:1,0,載入音訊中...", flush=True)

        audio = AudioFileClip(audio_path)
        y, sr = librosa.load(audio_path, sr=22050)

        hop_length = 512
        n_mels = 320

        print("PROGRESS:1,30,計算 Mel 頻譜...", flush=True)
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=2048,
                                             hop_length=hop_length, n_mels=n_mels)
        freq_data = librosa.power_to_db(mel, ref=np.max)

        freq_data = (freq_data + 80) / 80
        freq_data = np.clip(freq_data, 0, 1)

        row_max = np.max(freq_data, axis=1, keepdims=True)
        row_max[row_max < 0.1] = 1
        freq_data = freq_data / row_max

        print("PROGRESS:1,60,平滑化頻譜...", flush=True)
        for i in range(1, freq_data.shape[1]):
            freq_data[:, i] = freq_data[:, i] * 0.4 + freq_data[:, i - 1] * 0.6

        n_frames_audio = freq_data.shape[1]

        def get_frame_idx(t):
            idx = int(t * sr / hop_length)
            return min(idx, n_frames_audio - 1)

        print("PROGRESS:1,100,完成", flush=True)

        width, height = 1920, 1080
        bg = np.zeros((height, width, 3), dtype=np.uint8)
        bg[:] = [15, 10, 20]

        bar_width  = 2
        gap_width  = 4
        slot_width = bar_width + gap_width
        max_bar_height = int(height * 0.10)

        colors = [get_rainbow_color(i, n_mels) for i in range(n_mels)]
        duration = audio.duration

        print(f"LOG:音訊時長：{duration:.1f}s，開始渲染影片（fps=30）...", flush=True)
        print("PROGRESS:2,0,渲染中...", flush=True)

        last_reported = [0]

        def make_frame(t):
            pct = int(t / duration * 100)
            if pct >= last_reported[0] + 5:
                last_reported[0] = pct
                print(f"PROGRESS:2,{pct},{t:.1f}/{duration:.1f}s", flush=True)

            idx = get_frame_idx(t)
            current_data = freq_data[:, idx]
            frame = bg.copy()

            for i, val in enumerate(current_data):
                bar_height = max(2, int(val * max_bar_height))
                x1 = i * slot_width
                x2 = x1 + bar_width
                y2 = height - bar_height
                cv2.rectangle(frame, (x1, height), (x2, y2), colors[i], -1)

            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        clip  = VideoClip(make_frame, duration=duration)
        video = clip.with_audio(audio)

        print("LOG:寫入影片檔案...", flush=True)
        video.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac",
                              logger=None)

        print("PROGRESS:2,100,完成", flush=True)
        print(f"DONE:{output_path}", flush=True)

    try:
        make_video(audio_path, output_path)
    except Exception as e:
        import traceback
        print(f"ERROR:{e}\n{traceback.format_exc()}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
