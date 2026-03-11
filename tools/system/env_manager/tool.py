import argparse
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from core.base_tool import BaseTool
from core.isolated_tool import _find_conda_exe, _parse_conda_env_list


class EnvManagerTool(BaseTool):
    name = "env_manager"
    display_name = "環境管理"
    category = "system"
    description = "管理 conda 虛擬環境：列出、刪除"

    def add_cli_args(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="action")
        sub.add_parser("list", help="列出所有 conda 環境")
        rm = sub.add_parser("remove", help="移除 conda 環境")
        rm.add_argument("env_name", help="要移除的環境名稱")

    def run_cli(self, args) -> None:
        conda = _find_conda_exe()
        if args.action == "list":
            for name, path in _parse_conda_env_list(conda):
                print(f"{name:<25} {path}")
        elif args.action == "remove":
            if args.env_name == "base":
                print("[錯誤] 不可移除 base 環境")
                return
            print(f"移除環境: {args.env_name}")
            subprocess.run([conda, "remove", "--name", args.env_name, "--all", "-y"])
        else:
            print("用法: python run.py env_manager list|remove <name>")

    def get_ui_panel(self, parent: tk.Widget) -> tk.Widget:
        return _EnvManagerPanel(parent)


class _EnvManagerPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._envs: list[tuple[str, str]] = []  # [(name, path), ...]
        self._build()
        self.after(100, self._refresh)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        ttk.Label(self, text="環境管理", font=("", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self, text="列出並移除 conda 虛擬環境", foreground="gray").pack()

        # Toolbar
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=20, pady=(12, 4))
        self._btn_refresh = ttk.Button(bar, text="重新整理", command=self._refresh)
        self._btn_refresh.pack(side="left")
        self._btn_remove = ttk.Button(bar, text="移除選取環境", command=self._confirm_remove, state="disabled")
        self._btn_remove.pack(side="left", padx=8)
        self._status_lbl = ttk.Label(bar, text="", foreground="gray")
        self._status_lbl.pack(side="left", padx=4)

        # Environment list
        list_frame = ttk.LabelFrame(self, text="conda 環境", padding=6)
        list_frame.pack(fill="both", expand=False, padx=20, pady=(0, 8))

        cols = ("name", "path")
        self._tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=8, selectmode="browse")
        self._tree.heading("name", text="環境名稱")
        self._tree.heading("path", text="路徑")
        self._tree.column("name", width=180, stretch=False)
        self._tree.column("path", width=480, stretch=True)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Log
        log_frame = ttk.LabelFrame(self, text="執行紀錄", padding=6)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self._log = scrolledtext.ScrolledText(log_frame, state="disabled", font=("Consolas", 9), height=8)
        self._log.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_append(self, msg: str):
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _on_select(self, _=None):
        sel = self._tree.selection()
        env_name = self._tree.item(sel[0], "values")[0] if sel else ""
        # Disable remove for base environment
        self._btn_remove.config(state="normal" if (sel and env_name != "base") else "disabled")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        self._btn_refresh.config(state="disabled")
        self._status_lbl.config(text="掃描中...")
        self._tree.delete(*self._tree.get_children())
        self._btn_remove.config(state="disabled")

        def worker():
            conda = _find_conda_exe()
            envs = _parse_conda_env_list(conda)
            self.after(0, self._on_refresh_done, envs)

        threading.Thread(target=worker, daemon=True).start()

    def _on_refresh_done(self, envs: list):
        self._envs = envs
        self._tree.delete(*self._tree.get_children())
        for name, path in envs:
            tag = "base_row" if name == "base" else ""
            self._tree.insert("", "end", values=(name, path), tags=(tag,))
        self._tree.tag_configure("base_row", foreground="gray")
        self._status_lbl.config(text=f"共 {len(envs)} 個環境")
        self._btn_refresh.config(state="normal")

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def _confirm_remove(self):
        sel = self._tree.selection()
        if not sel:
            return
        env_name = self._tree.item(sel[0], "values")[0]
        env_path = self._tree.item(sel[0], "values")[1]
        if env_name == "base":
            messagebox.showwarning("警告", "不可移除 base 環境")
            return
        if not messagebox.askyesno(
            "確認移除",
            f"確定要移除環境「{env_name}」嗎？\n\n路徑：{env_path}\n\n此操作無法復原。",
        ):
            return
        self._do_remove(env_name)

    def _do_remove(self, env_name: str):
        self._btn_remove.config(state="disabled")
        self._btn_refresh.config(state="disabled")
        self._status_lbl.config(text=f"移除中：{env_name}...")
        self._log_append(f"[移除] conda remove --name {env_name} --all -y")

        def worker():
            conda = _find_conda_exe()
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            try:
                proc = subprocess.Popen(
                    [conda, "remove", "--name", env_name, "--all", "-y"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    env=env,
                )
                for line in proc.stdout:
                    self.after(0, self._log_append, line.rstrip())
                proc.wait()
                if proc.returncode == 0:
                    self.after(0, self._log_append, f"[完成] 環境 {env_name} 已移除")
                    self.after(0, self._refresh)
                else:
                    self.after(0, self._log_append, f"[失敗] 指令回傳代碼 {proc.returncode}")
                    self.after(0, self._on_remove_done)
            except Exception as e:
                self.after(0, self._log_append, f"[例外] {e}")
                self.after(0, self._on_remove_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_remove_done(self):
        self._btn_refresh.config(state="normal")
        self._status_lbl.config(text="")
        self._on_select()
