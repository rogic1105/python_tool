"""Graphical User Interface for the Invoice Helper."""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import invoice_lib

def calculate():
    target_str = target_entry.get().strip()
    numbers_str = numbers_text.get("1.0", "end-1c")

    if not target_str:
        messagebox.showwarning("Error", "Please enter a target number.")
        return

    try:
        target = int(target_str)
        numbers = [int(x) for x in numbers_str.split()]
    except ValueError:
        messagebox.showerror("Error", "Invalid input. Please use integers.")
        return

    if not numbers:
        return

    # Using the efficient DP solution
    closest, combination = invoice_lib.solve_dp(target, numbers)

    result_text = (
        f"Target: {target}\n"
        f"Best Sum: {closest} (Diff: {target - closest})\n"
        f"Combination: {combination}"
    )
    result_label.config(text=result_text)

root = tk.Tk()
root.title("Invoice Helper")
root.geometry("400x500")

tk.Label(root, text="Target:").pack(pady=5)
target_entry = tk.Entry(root)
target_entry.pack()

tk.Label(root, text="Numbers:").pack(pady=5)
numbers_text = scrolledtext.ScrolledText(root, height=15)
numbers_text.pack(padx=10)

tk.Button(root, text="Calculate", command=calculate).pack(pady=10)
result_label = tk.Label(root, text="Result will be shown here", wraplength=380)
result_label.pack(pady=10)

root.mainloop()