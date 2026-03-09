"""IsolatedPanel — GUI wrapper for IsolatedTool.

States:
  1. is_ready=True  → show tool's _build_panel() directly
  2. is_ready=False → VSCode-style env picker:
       a. Background scan: quickly list all Python envs (no import check)
       b. User selects one → verify only that env's packages
       c. User confirms → save & switch to ready state

Thread-safety:
  Background threads communicate back via self.after().
  _scan_cancelled / _verify_cancelled flags let threads exit early.
  Every callback checks _alive() before touching widgets.
"""

import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox


class IsolatedPanel(ttk.Frame):
    def __init__(self, parent, tool):
        super().__init__(parent)
        self.tool = tool
        self._scan_cancelled = False
        self._verify_cancelled = False
        self._listbox = None
        self._detected: list = []          # envs found so far (no has_packages yet)
        self._verify_result = None         # True / False / None for current selection
        self._render()

    # ------------------------------------------------------------------
    # Widget alive guard
    # ------------------------------------------------------------------

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def destroy(self):
        self._scan_cancelled = True
        self._verify_cancelled = True
        super().destroy()

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _render(self):
        self._scan_cancelled = True
        self._verify_cancelled = True
        for child in self.winfo_children():
            child.destroy()
        self._listbox = None
        self._detected = []
        self._verify_result = None
        self._scan_cancelled = False
        self._verify_cancelled = False
        if self.tool.is_ready:
            self._build_ready_panel()
        else:
            self._build_picker_panel()

    # ------------------------------------------------------------------
    # Ready state
    # ------------------------------------------------------------------

    def _build_ready_panel(self):
        info_bar = ttk.Frame(self)
        info_bar.pack(fill="x", padx=8, pady=(4, 0))
        ttk.Label(
            info_bar,
            text=f"環境: {self.tool.active_python}",
            foreground="gray",
            font=("Consolas", 8),
        ).pack(side="left")
        ttk.Button(info_bar, text="更換環境", command=self._reset_and_repick).pack(side="right")

        try:
            panel = self.tool._build_panel(self)
            panel.pack(fill="both", expand=True)
        except Exception as e:
            ttk.Label(self, text=f"載入工具面板失敗：{e}", foreground="red").pack(pady=30)

    def _reset_and_repick(self):
        self.tool.clear_saved_python()
        self._render()

    # ------------------------------------------------------------------
    # Env-picker panel
    # ------------------------------------------------------------------

    def _build_picker_panel(self):
        ttk.Label(self, text=self.tool.display_name, font=("", 13, "bold")).pack(pady=(15, 3))
        ttk.Label(self, text="選擇 Python 環境", foreground="gray").pack()

        # --- Env list ---
        list_frame = ttk.LabelFrame(self, text="偵測到的環境", padding=8)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(10, 4))

        lb_frame = ttk.Frame(list_frame)
        lb_frame.pack(fill="both", expand=True)

        sb = ttk.Scrollbar(lb_frame, orient="vertical")
        sb.pack(side="right", fill="y")

        self._listbox = tk.Listbox(
            lb_frame, yscrollcommand=sb.set, font=("Consolas", 10),
            selectmode="single", activestyle="none",
            relief="flat", bd=0, highlightthickness=1,
        )
        self._listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self._listbox.yview)

        # Scanning status (shown while scanning)
        self._scan_status_var = tk.StringVar(value="  正在掃描環境...")
        self._scan_status_lbl = ttk.Label(
            list_frame, textvariable=self._scan_status_var,
            foreground="gray", font=("", 8),
        )
        self._scan_status_lbl.pack(anchor="w", pady=(4, 0))

        # --- Package verification status ---
        verify_frame = ttk.Frame(self)
        verify_frame.pack(fill="x", padx=20, pady=(0, 4))
        ttk.Label(verify_frame, text="套件狀態：").pack(side="left")
        self._verify_var = tk.StringVar(value="—")
        self._verify_lbl = ttk.Label(
            verify_frame, textvariable=self._verify_var,
            font=("Consolas", 9),
        )
        self._verify_lbl.pack(side="left")

        # --- Manual path ---
        manual_frame = ttk.LabelFrame(self, text="手動指定 Python 路徑", padding=8)
        manual_frame.pack(fill="x", padx=20, pady=(0, 6))
        manual_row = ttk.Frame(manual_frame)
        manual_row.pack(fill="x")
        self._manual_var = tk.StringVar()
        ttk.Entry(manual_row, textvariable=self._manual_var).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        ttk.Button(manual_row, text="瀏覽", command=self._browse_python).pack(side="left")

        # --- Action buttons ---
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=20, pady=(0, 4))
        self.btn_use = ttk.Button(
            btn_frame, text="使用此環境",
            command=self._use_selected, state="disabled",
        )
        self.btn_use.pack(fill="x")

        new_frame = ttk.Frame(self)
        new_frame.pack(fill="x", padx=20, pady=(0, 8))
        self.btn_new_venv = ttk.Button(
            new_frame, text="新建 venv 環境",
            command=self._start_create_venv,
        )
        self.btn_new_venv.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_new_conda = ttk.Button(
            new_frame, text="新建 conda 環境",
            command=self._start_create_conda_env,
        )
        self.btn_new_conda.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Install log (hidden until needed)
        self._log_frame = ttk.LabelFrame(self, text="安裝紀錄", padding=6)
        self._install_log = scrolledtext.ScrolledText(
            self._log_frame, height=7, state="disabled", font=("Consolas", 9)
        )
        self._install_log.pack(fill="both", expand=True)

        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self._manual_var.trace_add("write", lambda *_: self._on_manual_changed())

        # Start background env scan (fast — no import check)
        threading.Thread(target=self._scan_envs, daemon=True).start()

    # ------------------------------------------------------------------
    # Background env scan  (fast: only finds Python binaries)
    # ------------------------------------------------------------------

    def _scan_envs(self):
        from core.isolated_tool import scan_candidate_envs

        candidates = scan_candidate_envs()

        for c in candidates:
            if self._scan_cancelled:
                return
            self._detected.append(c)
            label = f"  {c['label']}"

            def _insert(lbl=label):
                if not self._alive() or self._listbox is None:
                    return
                self._listbox.insert("end", lbl)

            self.after(0, _insert)

        def _done():
            if not self._alive():
                return
            count = len(self._detected)
            if count == 0:
                if self._listbox:
                    self._listbox.insert("end", "  未偵測到任何 Python 環境")
                self._scan_status_var.set("  未找到環境")
            else:
                self._scan_status_var.set(f"  共找到 {count} 個環境，請選擇一個")

        self.after(0, _done)

    # ------------------------------------------------------------------
    # Package verification  (triggered on selection, runs in daemon thread)
    # ------------------------------------------------------------------

    def _on_list_select(self, _event=None):
        if not self._alive() or self._listbox is None:
            return
        sel = self._listbox.curselection()
        if not sel:
            return

        idx = sel[0]
        if idx >= len(self._detected):
            return

        env = self._detected[idx]
        self.btn_use.config(state="normal")   # allow use even before verify finishes

        # Cancel any in-progress verification
        self._verify_cancelled = True
        self._verify_cancelled = False

        self._verify_var.set("驗證中...")
        self._verify_lbl.config(foreground="gray")
        self._verify_result = None

        threading.Thread(
            target=self._verify_env,
            args=(env["python"], idx),
            daemon=True,
        ).start()

    def _verify_env(self, python: str, list_idx: int):
        from core.isolated_tool import _verify_imports
        has = _verify_imports(python, self.tool.check_imports)

        if self._verify_cancelled:
            return

        def _update():
            if not self._alive():
                return
            # Only update if the same item is still selected
            sel = self._listbox.curselection() if self._listbox else ()
            if not sel or sel[0] != list_idx:
                return
            self._verify_result = has
            if has:
                self._verify_var.set("✓ 所需套件齊全")
                self._verify_lbl.config(foreground="#006400")
            else:
                missing = ", ".join(self.tool.check_imports)
                self._verify_var.set(f"✗ 缺少套件：{missing}")
                self._verify_lbl.config(foreground="#cc0000")

        self.after(0, _update)

    def _on_manual_changed(self):
        if not self._alive():
            return
        manual = self._manual_var.get().strip()
        if self.btn_use.winfo_exists():
            self.btn_use.config(state="normal" if manual else "disabled")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_python(self):
        path = filedialog.askopenfilename(
            title="選擇 Python 執行檔",
            filetypes=[("Python", "python python3 python.exe"), ("All", "*")],
        )
        if path:
            self._manual_var.set(path)

    def _use_selected(self):
        manual = self._manual_var.get().strip()
        if manual:
            python = manual
        else:
            sel = self._listbox.curselection() if self._listbox else ()
            if not sel:
                return messagebox.showwarning("提示", "請先選擇一個環境")
            idx = sel[0]
            if idx >= len(self._detected):
                return
            python = self._detected[idx]["python"]

        # If verification hasn't finished or failed, warn user
        if self._verify_result is False:
            if not messagebox.askyesno(
                "套件缺失",
                f"此環境缺少所需套件：\n{', '.join(self.tool.check_imports)}\n\n"
                "仍要使用此環境嗎？（工具可能無法正常運作）",
            ):
                return

        self.tool.save_active_python(python)
        self._render()

    def _start_create_venv(self):
        self._log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self.btn_new_venv.config(state="disabled")
        self.btn_new_conda.config(state="disabled")
        self.btn_use.config(state="disabled")

        def worker():
            try:
                self.tool.setup_venv(log_cb=lambda m: self.after(0, self._append_log, m))
                if self._alive():
                    self.after(0, self._render)
            except Exception as e:
                if self._alive():
                    self.after(0, self._append_log, f"[錯誤] {e}")
                    self.after(0, lambda: [
                        self.btn_new_venv.config(state="normal"),
                        self.btn_new_conda.config(state="normal"),
                    ])

        threading.Thread(target=worker, daemon=True).start()

    def _start_create_conda_env(self):
        """Show a dialog to confirm env name & Python version, then create conda env."""
        dlg = tk.Toplevel(self)
        dlg.title("新建 conda 環境")
        dlg.resizable(False, False)
        dlg.grab_set()

        ttk.Label(dlg, text="環境名稱:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        env_name_var = tk.StringVar(value=f"{self.tool.venv_name}-env")
        ttk.Entry(dlg, textvariable=env_name_var, width=28).grid(row=0, column=1, padx=(0, 12), pady=8)

        ttk.Label(dlg, text="Python 版本:").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        py_ver_var = tk.StringVar(value="3.10")
        ver_cb = ttk.Combobox(dlg, textvariable=py_ver_var, width=10,
                              values=["3.9", "3.10", "3.11", "3.12"], state="readonly")
        ver_cb.grid(row=1, column=1, padx=(0, 12), pady=4, sticky="w")

        req_path = self.tool._resolve_requirements()
        ttk.Label(
            dlg,
            text=f"將安裝: {req_path.name}",
            foreground="gray", font=("", 8),
        ).grid(row=2, column=0, columnspan=2, padx=12, pady=(2, 8))

        def on_confirm():
            name = env_name_var.get().strip()
            ver  = py_ver_var.get().strip()
            if not name:
                messagebox.showwarning("提示", "請輸入環境名稱", parent=dlg)
                return
            dlg.destroy()
            self._run_create_conda_env(name, ver)

        btn_row = ttk.Frame(dlg)
        btn_row.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_row, text="建立", command=on_confirm).pack(side="left", padx=8)
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side="left", padx=8)

    def _run_create_conda_env(self, env_name: str, python_version: str):
        self._log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self.btn_new_venv.config(state="disabled")
        self.btn_new_conda.config(state="disabled")
        self.btn_use.config(state="disabled")

        def worker():
            try:
                self.tool.setup_conda_env(
                    env_name=env_name,
                    python_version=python_version,
                    log_cb=lambda m: self.after(0, self._append_log, m),
                )
                if self._alive():
                    self.after(0, self._render)
            except Exception as e:
                if self._alive():
                    self.after(0, self._append_log, f"[錯誤] {e}")
                    self.after(0, lambda: [
                        self.btn_new_venv.config(state="normal"),
                        self.btn_new_conda.config(state="normal"),
                    ])

        threading.Thread(target=worker, daemon=True).start()

    def _append_log(self, msg: str):
        if not self._alive():
            return
        self._install_log.config(state="normal")
        self._install_log.insert("end", msg + "\n")
        self._install_log.see("end")
        self._install_log.config(state="disabled")
