#!/usr/bin/env python3
"""Standalone invoice helper runner — no framework imports.

Output protocol:
  LOG:<message>
  TEXT:<result line>
  DONE:
  ERROR:<message>
"""

import sys
import os
import json
import argparse

# Force UTF-8 stdout/stderr on Windows. Use reconfigure() to avoid GC closing the buffer.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

BRUTE_FORCE_LIMIT = 22


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--numbers", required=True, help="JSON array of integers")
    args = parser.parse_args()

    from invoice_lib import solve_dp, solve_brute_force
    import time

    target = args.target
    numbers = json.loads(args.numbers)

    print(f"LOG:目標: {target}，共 {len(numbers)} 筆", flush=True)
    print(f"TEXT:{'=' * 40}", flush=True)

    t0 = time.time()
    s_dp, c_dp = solve_dp(target, numbers)
    print(f"TEXT:[DP]  結果: {s_dp}  差額: {target - s_dp}  耗時: {time.time() - t0:.4f} 秒", flush=True)
    print(f"TEXT:  組合: {c_dp}", flush=True)
    print(f"TEXT:{'-' * 40}", flush=True)

    if len(numbers) > BRUTE_FORCE_LIMIT:
        print(f"TEXT:[暴力法] 略過（N={len(numbers)} > {BRUTE_FORCE_LIMIT}，計算量過大）", flush=True)
    else:
        t0 = time.time()
        s_bf, c_bf = solve_brute_force(target, numbers)
        print(f"TEXT:[BF]  結果: {s_bf}  差額: {target - s_bf}  耗時: {time.time() - t0:.4f} 秒", flush=True)
        match = "相符" if s_dp == s_bf else "不符！"
        print(f"TEXT:  兩法結果{match}", flush=True)

    print("DONE:", flush=True)


if __name__ == "__main__":
    main()
