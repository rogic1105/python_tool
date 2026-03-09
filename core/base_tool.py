from abc import ABC, abstractmethod
import argparse
import tkinter as tk
from tkinter import ttk


class BaseTool(ABC):
    name: str = ""
    display_name: str = ""
    category: str = ""
    description: str = ""

    @abstractmethod
    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        pass

    @abstractmethod
    def run_cli(self, args) -> None:
        pass

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _DefaultPanel(parent, self)


class _DefaultPanel(ttk.Frame):
    def __init__(self, parent, tool: "BaseTool"):
        super().__init__(parent)
        ttk.Label(self, text=tool.display_name, font=("", 14, "bold")).pack(pady=20)
        ttk.Label(self, text=tool.description, wraplength=400).pack()
        ttk.Label(self, text="此工具暫無 GUI 面板，請使用 CLI：", foreground="gray").pack(pady=10)
        ttk.Label(self, text=f"python run.py {tool.name} --help", font=("Courier", 10)).pack()
