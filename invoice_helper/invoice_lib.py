"""Core logic for the Invoice Helper application.

This module implements:
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
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            
            if not lines:
                return None, None
                
            target = int(lines[0])
            numbers = [int(line) for line in lines[1:]]
            return target, numbers
            
    except (IOError, ValueError) as e:
        print(f"Error reading file '{file_path}': {e}", file=sys.stderr)
        return None, None


def solve_dp(target: int, numbers: List[int]) -> Tuple[int, List[int]]:
    """Finds closest subset sum using Dynamic Programming (Knapsack-like).
    
    Returns:
        (closest_sum, combination_list) where closest_sum <= target.
    """
    n = len(numbers)
    # dp[j] stores the max sum <= j found so far
    dp = np.zeros(target + 1, dtype=int)
    # path for reconstruction
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
    """Finds closest subset sum by iterating all 2^N combinations.
    
    WARNING: Extremely slow for len(numbers) > 22.
    
    Returns:
        (closest_sum, combination_list) where closest_sum <= target.
    """
    n = len(numbers)
    best_sum = 0
    best_combination = []

    # Iterate through all possible lengths of combinations (1 to n)
    # Using itertools is generally faster than manual binary loop
    for r in range(1, n + 1):
        for combination in itertools.combinations(numbers, r):
            current_sum = sum(combination)
            
            # We want the largest sum that is still <= target
            if best_sum < current_sum <= target:
                best_sum = current_sum
                best_combination = list(combination)
                
                # Optimization: If we hit the target exactly, stop early
                if best_sum == target:
                    return best_sum, best_combination
    
    return best_sum, best_combination