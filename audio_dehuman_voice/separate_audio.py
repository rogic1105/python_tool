import os
import subprocess
import shutil

# --- 設定區 ---
DEMUCS_MODEL = "htdemucs"  # 使用最強模型
INPUT_FILE = "data/test.mp3" # 你的輸入檔案
OUTPUT_FOLDER = "output" # 結果存哪裡

def run_better_demucs(input_path, output_dir):
    """
    使用 Demucs 原生功能進行分離
    不需要手動切片，Demucs 會自動處理長音訊
    """
    os.makedirs(output_dir, exist_ok=True)
    
    command = [
        "demucs",
        "-n", DEMUCS_MODEL,       # 指定模型
        "--two-stems=vocals",     # 指定只要分離人聲 (另一軌會自動變成 no_vocals)
        "-o", output_dir,         # 輸出路徑
        # "--mp3",                # 如果你想直接輸出 mp3 省空間，可以把這行註解打開
        # "--float32",            # 如果你需要極高音質 (32-bit float wav)，打開這行
        input_path
    ]
    
    print(f"🚀 開始處理: {input_path}")
    print("Demucs 正在自動處理長音訊 (包含自動切片與無縫接合)...")
    
    try:
        # capture_output=True 會把進度條隱藏，如果你想看進度條，可以改成 capture_output=False
        result = subprocess.run(command, check=True, text=True)
        print("✅ 處理完成！")
    except subprocess.CalledProcessError as e:
        print("❌ 錯誤！")
        print(e.stderr)

if __name__ == '__main__':
    # 取得絕對路徑，比較保險
    cwd = os.getcwd()
    full_input_path = os.path.join(cwd, INPUT_FILE)
    full_output_path = os.path.join(cwd, OUTPUT_FOLDER)

    if not os.path.exists(full_input_path):
        print(f"找不到檔案: {full_input_path}")
        exit(1)

    # 執行
    run_better_demucs(full_input_path, full_output_path)
    
    # 告訴使用者檔案在哪
    # Demucs 的輸出結構: output_dir / model_name / file_name / vocals.wav
    filename = os.path.splitext(os.path.basename(INPUT_FILE))[0]
    final_folder = os.path.join(full_output_path, DEMUCS_MODEL, filename)
    
    print("\n檔案輸出位置：")
    print(f"📂 資料夾: {final_folder}")
    print(f"🎤 人聲: {os.path.join(final_folder, 'vocals.wav')}")
    print(f"🎹 伴奏: {os.path.join(final_folder, 'no_vocals.wav')}")

