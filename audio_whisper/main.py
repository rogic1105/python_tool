import argparse
import sys
from src.config import setup_env, DEFAULT_OUTPUT_DIR
from src.logic import Pipeline
from tqdm import tqdm

def run_cli(args):
    pipeline = Pipeline(DEFAULT_OUTPUT_DIR)

    # CLI 用一個簡單的進度條來顯示總體感覺，不分三條
    pbar = tqdm(total=100, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]')
    
    def cli_log(msg):
        tqdm.write(f"[Log] {msg}")
        
    def cli_progress(stage, val, msg):
        # 簡單映射：Stage 1=0-10%, Stage 2=10-40%, Stage 3=40-100%
        if stage == 1:
            pbar.n = int(val * 0.1)
        elif stage == 2:
            pbar.n = 10 + int(val * 0.3)
        elif stage == 3:
            pbar.n = 40 + int(val * 0.6)
        
        desc = f"Stage {stage}"
        if msg: desc += f" ({msg})"
        pbar.set_description(desc)
        pbar.refresh()

    def cli_transcript(text):
        tqdm.write(f"[Text] {text}")
        
    try:
        pipeline.run(
            args.input, args.model, args.language, args.speakers,
            log_cb=cli_log, 
            progress_cb=cli_progress,
            transcript_cb=cli_transcript
        )
        pbar.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    setup_env()
    
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="Input audio file")
    parser.add_argument("--gui", action="store_true", help="Launch GUI")
    parser.add_argument("--model", default="medium")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--speakers", type=int, default=0)
    
    args = parser.parse_args()
    
    if args.gui or not args.input:
        from src.gui import App
        app = App()
        app.mainloop()
    else:
        run_cli(args)