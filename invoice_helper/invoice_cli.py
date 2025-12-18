"""Command-line interface to compare DP and Brute Force algorithms."""

import time
import invoice_lib

# Warning threshold for brute force
BRUTE_FORCE_LIMIT = 22

def main():
    """Main execution function."""
    file_path = 'price.txt'
    print(f"Reading data from {file_path}...")
    target, numbers = invoice_lib.read_price_data(file_path)

    if target is None:
        print("Failed to load data.")
        return

    n = len(numbers)
    print(f"Target: {target}")
    print(f"Numbers count: {n}")
    print("=" * 40)

    # --- 1. Run Dynamic Programming ---
    print("[Dynamic Programming] Running...")
    start_dp = time.time()
    sum_dp, comb_dp = invoice_lib.solve_dp(target, numbers)
    time_dp = time.time() - start_dp
    print(f"  Result: {sum_dp} (Diff: {target - sum_dp})")
    print(f"  Time:   {time_dp:.6f} sec")
    print("-" * 40)

    # --- 2. Run Brute Force (Conditional) ---
    if n > BRUTE_FORCE_LIMIT:
        print(f"[Brute Force] Skipped. (Input size {n} > {BRUTE_FORCE_LIMIT} is too large)")
        print("  Brute force complexity is O(2^N). It would take too long.")
    else:
        print("[Brute Force] Running...")
        start_bf = time.time()
        sum_bf, comb_bf = invoice_lib.solve_brute_force(target, numbers)
        time_bf = time.time() - start_bf
        print(f"  Result: {sum_bf} (Diff: {target - sum_bf})")
        print(f"  Time:   {time_bf:.6f} sec")
        
        # Validation
        if sum_dp == sum_bf:
            print("\n[Match] Both algorithms found the same optimal sum.")
        else:
            print(f"\n[Mismatch!] DP: {sum_dp}, BF: {sum_bf}")

    print("=" * 40)
    print(f"DP Combination: {comb_dp}")
    time.sleep(3)

if __name__ == '__main__':
    main()