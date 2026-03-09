#!/usr/bin/env python3
"""Unified GUI entry point for Python Tools.

Usage:
    python ui.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import tkinter as tk
from tkinter import ttk

from core.registry import discover_tools, CATEGORY_LABELS


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Python Tools")
        self.geometry("1050x720")
        self.minsize(800, 500)

        try:
            self.tk.call("tk", "scaling", 1.5)
        except Exception:
            pass

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        tools_by_cat = discover_tools()

        for cat, label in CATEGORY_LABELS.items():
            tools = tools_by_cat.get(cat, [])
            if not tools:
                continue
            cat_frame = ttk.Frame(notebook)
            notebook.add(cat_frame, text=f"  {label}  ")
            self._build_category_tab(cat_frame, tools)

        ttk.Label(self, text="Python Tools  |  python run.py --help", foreground="gray", font=("", 8)).pack(
            side="bottom", anchor="e", padx=10, pady=2
        )

    def _build_category_tab(self, parent: ttk.Frame, tools: list):
        pw = ttk.PanedWindow(parent, orient="horizontal")
        pw.pack(fill="both", expand=True)

        # Left: tool selector
        left = ttk.Frame(pw, width=190)
        pw.add(left, weight=0)

        ttk.Label(left, text="工具選擇", font=("", 10, "bold")).pack(pady=(12, 4), padx=8, anchor="w")

        listbox = tk.Listbox(
            left,
            selectmode="single",
            font=("", 11),
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        listbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        for t in tools:
            listbox.insert("end", f"  {t.display_name}")

        # Tool description label
        desc_label = ttk.Label(left, text="", wraplength=175, foreground="gray", font=("", 8), justify="left")
        desc_label.pack(padx=8, pady=(0, 8), anchor="w")

        # Right: panel container
        right = ttk.Frame(pw)
        pw.add(right, weight=1)

        current_panel = [None]

        def on_select(event=None):
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            tool = tools[idx]

            desc_label.config(text=tool.description)

            if current_panel[0] is not None:
                current_panel[0].pack_forget()
                current_panel[0].destroy()

            try:
                panel = tool.get_ui_panel(right)
            except Exception as e:
                panel = _ErrorPanel(right, str(e))

            panel.pack(fill="both", expand=True)
            current_panel[0] = panel

        listbox.bind("<<ListboxSelect>>", on_select)

        # Show first tool by default
        if tools:
            listbox.selection_set(0)
            on_select()


class _ErrorPanel(ttk.Frame):
    def __init__(self, parent, error_msg: str):
        super().__init__(parent)
        ttk.Label(self, text="載入工具時發生錯誤", font=("", 13, "bold"), foreground="red").pack(pady=30)
        ttk.Label(self, text=error_msg, foreground="gray", wraplength=500).pack()


def main():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
