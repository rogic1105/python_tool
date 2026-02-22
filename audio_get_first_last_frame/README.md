# Video Frame Extractor

從影片中提取第一幀和最後一幀並儲存為圖片。

## 功能特點

- 提取影片的第一幀和最後一幀
- 使用 ffmpeg 保留原始色彩空間，確保色彩準確
- 支援各種影片格式（.mov, .mp4, .avi 等）
- 自動生成輸出檔名或自訂前綴

## 系統需求

- Python 3.x
- ffmpeg 和 ffprobe（需安裝在系統中）

### 安裝 ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Windows:**
從 [ffmpeg.org](https://ffmpeg.org/download.html) 下載並加入系統 PATH

## 使用方法

### 基本用法

```bash
python audio_get_last_frame.py <影片檔案>
```

**範例:**
```bash
python audio_get_last_frame.py video.mov
```

輸出檔案：
- `video_first_frame.png` - 第一幀
- `video_last_frame.png` - 最後一幀

### 自訂輸出檔名前綴

```bash
python audio_get_last_frame.py <影片檔案> <輸出前綴>
```

**範例:**
```bash
python audio_get_last_frame.py video.mov output
```

輸出檔案：
- `output_first_frame.png` - 第一幀
- `output_last_frame.png` - 最後一幀

## 技術說明

- 使用 `ffmpeg` 直接提取幀，避免色彩空間轉換造成的色差
- 第一幀：使用 `select=eq(n,0)` 濾鏡精確提取
- 最後一幀：使用 `-sseof -1` 從影片結尾前 1 秒開始尋找
- 輸出格式：PNG（無損壓縮）

## 錯誤處理

腳本會檢查：
- 影片檔案是否存在
- ffmpeg/ffprobe 是否正確安裝
- 影片是否包含有效的視訊串流

## License

MIT
