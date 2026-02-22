# src/processor.py
import os
import subprocess
import threading
import re
import shutil  # [新增] 用來搬移檔案

DEMUCS_MODEL = "htdemucs"
current_process = None

def stop_process():
    global current_process
    if current_process and current_process.poll() is None:
        current_process.terminate()
        print("🛑 已發送終止訊號...")

def run_demucs_thread(input_path, output_dir, log_callback, progress_callback, done_callback):
    
    os.makedirs(output_dir, exist_ok=True)
    global current_process

    command = [
        "demucs",
        "-n", DEMUCS_MODEL,
        "--two-stems=vocals",
        "-o", output_dir,
        input_path
    ]

    log_callback(f"🚀 準備執行...\n")
    
    def target():
        global current_process
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            current_process = process
            progress_pattern = re.compile(r"^\s*(\d+)%\|")

            for line in process.stdout:
                match = progress_pattern.search(line)
                if match:
                    percentage = int(match.group(1))
                    progress_callback(percentage)
                else:
                    if line.strip(): 
                        log_callback(line)

            process.wait()

            if process.returncode == 0:
                progress_callback(100)
                log_callback("\n✅ 分離運算完成，正在整理檔案...\n")
                
                # --- [新增] 自動移動檔案邏輯 ---
                # 1. 取得檔案名稱 (不含副檔名)
                filename_no_ext = os.path.splitext(os.path.basename(input_path))[0]
                
                # 2. 定義原本 Demucs 產生的深層路徑 (output/htdemucs/song_name)
                deep_output_path = os.path.join(output_dir, DEMUCS_MODEL, filename_no_ext)
                
                # 3. 定義我們想要的目標路徑 (output/song_name)
                target_output_path = os.path.join(output_dir, filename_no_ext)

                try:
                    # 如果目標已經存在，先移除舊的，避免搬移失敗
                    if os.path.exists(target_output_path):
                        shutil.rmtree(target_output_path)
                    
                    # 開始搬移整個資料夾
                    shutil.move(deep_output_path, output_dir)
                    
                    # 嘗試移除空的模型資料夾 (output/htdemucs)
                    model_dir = os.path.join(output_dir, DEMUCS_MODEL)
                    if os.path.exists(model_dir) and not os.listdir(model_dir):
                        os.rmdir(model_dir)

                    log_callback(f"📂 檔案已移動至: {target_output_path}\n")
                    
                except Exception as move_error:
                    log_callback(f"⚠️ 檔案移動失敗，請檢查原始路徑: {move_error}\n")
                
                # --- [結束] 移動邏輯 ---

            elif process.returncode != 0 and process.returncode is not None:
                log_callback(f"\n🛑 程序已停止 (代碼: {process.returncode})\n")

        except Exception as e:
            log_callback(f"\n❌ 發生例外錯誤: {str(e)}\n")
        finally:
            current_process = None
            done_callback()

    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()