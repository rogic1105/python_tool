"""Core logic for the Invoice Helper application.

Implements:
1. File I/O operations.
2. Dynamic Programming (DP) algorithm for subset sum.
3. Brute Force algorithm for benchmarking and verification.
"""

import sys
import itertools
from typing import List, Tuple, Optional
import numpy as np


def read_price_data(file_path: str) -> Tuple[Optional[int], Optional[List[int]]]:
    """Reads target and price list from a text file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            return None, None
        target = int(lines[0])
        numbers = [int(line) for line in lines[1:]]
        return target, numbers
    except (IOError, ValueError) as e:
        print(f"Error reading file '{file_path}': {e}", file=sys.stderr)
        return None, None


def solve_dp(target: int, numbers: List[int]) -> Tuple[int, List[int]]:
    """Finds closest subset sum using Dynamic Programming."""
    n = len(numbers)
    dp = np.zeros(target + 1, dtype=int)
    path = np.zeros((target + 1, n), dtype=bool)

    for i in range(n):
        num = numbers[i]
        for j in range(target, num - 1, -1):
            if dp[j - num] + num > dp[j]:
                dp[j] = dp[j - num] + num
                path[j] = path[j - num]
                path[j, i] = True

    closest_sum = dp[target]
    combination = [numbers[i] for i in range(n) if path[target, i]]
    return closest_sum, combination


def solve_brute_force(target: int, numbers: List[int]) -> Tuple[int, List[int]]:
    """Finds closest subset sum by iterating all 2^N combinations. Slow for N > 22."""
    best_sum, best_comb = 0, []
    for r in range(1, len(numbers) + 1):
        for combo in itertools.combinations(numbers, r):
            s = sum(combo)
            if best_sum < s <= target:
                best_sum, best_comb = s, list(combo)
                if best_sum == target:
                    return best_sum, best_comb
    return best_sum, best_comb
