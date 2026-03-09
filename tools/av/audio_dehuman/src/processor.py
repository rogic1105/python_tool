import os
import subprocess
import threading
import re
import shutil

DEMUCS_MODEL = "htdemucs"
current_process = None


def stop_process():
    global current_process
    if current_process and current_process.poll() is None:
        current_process.terminate()


def run_demucs_thread(input_path, output_dir, log_callback, progress_callback, done_callback):
    os.makedirs(output_dir, exist_ok=True)
    global current_process

    command = ["demucs", "-n", DEMUCS_MODEL, "--two-stems=vocals", "-o", output_dir, input_path]
    log_callback("準備執行 Demucs...\n")

    def target():
        global current_process
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True
            )
            current_process = process
            progress_pattern = re.compile(r"^\s*(\d+)%\|")

            for line in process.stdout:
                match = progress_pattern.search(line)
                if match:
                    progress_callback(int(match.group(1)))
                elif line.strip():
                    log_callback(line)

            process.wait()

            if process.returncode == 0:
                progress_callback(100)
                log_callback("分離完成，整理檔案中...\n")
                filename_no_ext = os.path.splitext(os.path.basename(input_path))[0]
                deep_path = os.path.join(output_dir, DEMUCS_MODEL, filename_no_ext)
                target_path = os.path.join(output_dir, filename_no_ext)
                try:
                    if os.path.exists(target_path):
                        shutil.rmtree(target_path)
                    shutil.move(deep_path, output_dir)
                    model_dir = os.path.join(output_dir, DEMUCS_MODEL)
                    if os.path.exists(model_dir) and not os.listdir(model_dir):
                        os.rmdir(model_dir)
                    log_callback(f"檔案已移動至: {target_path}\n")
                except Exception as e:
                    log_callback(f"檔案移動失敗: {e}\n")
            elif process.returncode is not None and process.returncode != 0:
                log_callback(f"程序已停止 (代碼: {process.returncode})\n")

        except Exception as e:
            log_callback(f"發生例外錯誤: {e}\n")
        finally:
            current_process = None
            done_callback()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
