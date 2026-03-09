"""IsolatedTool — BaseTool extension for tools that require their own venv.

Environment selection priority:
  1. User-saved preference (stored in .venvs/env_config.json)
  2. Auto-detected existing envs that already have required packages
  3. Managed venv created by this framework (.venvs/<tool_name>/)

Output protocol for runner.py scripts:
  LOG:<message>
  PROGRESS:<stage>,<0-100>,<optional msg>
  TEXT:<transcript line>
  DONE:<output_path>
  ERROR:<message>
"""

import json
import os
import subprocess
import sys
import venv as _venv
from abc import abstractmethod
from pathlib import Path
from typing import List, Optional

from core.base_tool import BaseTool

PROJECT_ROOT = Path(__file__).parent.parent
VENVS_DIR    = PROJECT_ROOT / ".venvs"
ENV_CONFIG   = VENVS_DIR / "env_config.json"

PREFIX_LOG      = "LOG:"
PREFIX_PROGRESS = "PROGRESS:"
PREFIX_TEXT     = "TEXT:"
PREFIX_DONE     = "DONE:"
PREFIX_ERROR    = "ERROR:"


# ---------------------------------------------------------------------------
# Environment detection helpers (module-level, tool-independent)
# ---------------------------------------------------------------------------

def _python_in_dir(d: Path) -> Optional[str]:
    """Return the python executable path inside a venv/conda directory, or None."""
    for candidate in (d / "bin" / "python", d / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return None


def _verify_imports(python: str, import_names: List[str], timeout: int = 10) -> bool:
    """Return True if all import_names are importable by the given Python."""
    if not import_names:
        return True
    code = "; ".join(f"import {m}" for m in import_names)
    try:
        r = subprocess.run([python, "-c", code], capture_output=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def _python_label(python: str) -> str:
    """Get a short version label from a Python binary."""
    try:
        r = subprocess.run([python, "--version"], capture_output=True, text=True, timeout=5)
        return (r.stdout or r.stderr).strip()
    except Exception:
        return "Python"


def scan_candidate_envs(sources: Optional[List[str]] = None) -> List[dict]:
    """
    Return a list of dicts describing discovered Python environments:
      { "label": str, "python": str, "source": str }
    Does NOT verify whether any specific packages are present.

    sources: list of source types to include, or None for all.
      Valid values: "current", "conda", "managed", "local", "pyenv"
    """
    candidates = []
    seen = set()

    def want(src: str) -> bool:
        return sources is None or src in sources

    def add(label: str, python: str, source: str):
        real = str(Path(python).resolve())
        if real in seen or not Path(python).exists():
            return
        seen.add(real)
        candidates.append({"label": label, "python": python, "source": source})

    # 1. Current running Python
    if want("current"):
        add(f"目前環境 ({_python_label(sys.executable)})", sys.executable, "current")

    # 2. Conda environments
    if want("conda"):
        try:
            r = subprocess.run(
                ["conda", "env", "list", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            for env_path in json.loads(r.stdout).get("envs", []):
                p = _python_in_dir(Path(env_path))
                if p:
                    env_name = Path(env_path).name or "base"
                    add(f"conda: {env_name}  ({env_path})", p, "conda")
        except Exception:
            pass

    # 3. Our managed .venvs/<name>/ directories
    if want("managed") and VENVS_DIR.exists():
        for d in sorted(VENVS_DIR.iterdir()):
            if d.is_dir():
                p = _python_in_dir(d)
                if p:
                    add(f"managed: {d.name}  ({d})", p, "managed")

    # 4. Common venv names in project root and home
    if want("local"):
        for base in (PROJECT_ROOT, Path.home()):
            for name in (".venv", "venv", "env", ".env"):
                d = base / name
                p = _python_in_dir(d)
                if p:
                    add(f"venv: {d}", p, "local")

    # 5. pyenv versions
    if want("pyenv"):
        pyenv_root = Path(os.environ.get("PYENV_ROOT", Path.home() / ".pyenv"))
        versions_dir = pyenv_root / "versions"
        if versions_dir.exists():
            for ver in sorted(versions_dir.iterdir()):
                p = _python_in_dir(ver)
                if p:
                    add(f"pyenv: {ver.name}", p, "pyenv")

    return candidates


# ---------------------------------------------------------------------------
# IsolatedTool
# ---------------------------------------------------------------------------

class IsolatedTool(BaseTool):
    """BaseTool subclass whose heavy logic runs in a subprocess inside an isolated env."""

    venv_name: str = ""
    requirements_file: str = ""
    # Import names used to verify that an env has the required packages.
    # Example: ["faster_whisper", "resemblyzer"]
    check_imports: List[str] = []

    # ------------------------------------------------------------------
    # Active python resolution  (saved config → managed venv)
    # ------------------------------------------------------------------

    @property
    def venv_dir(self) -> Path:
        return VENVS_DIR / self.venv_name

    @property
    def venv_python(self) -> str:
        """Path to python inside the *managed* venv (may not exist yet)."""
        if sys.platform == "win32":
            return str(self.venv_dir / "Scripts" / "python.exe")
        return str(self.venv_dir / "bin" / "python")

    @property
    def active_python(self) -> str:
        """
        The Python that will actually be used to run this tool.
        Order: saved config > managed venv > (not ready)
        """
        saved = self._load_saved_python()
        if saved and Path(saved).exists():
            return saved
        return self.venv_python   # may not exist

    @property
    def is_ready(self) -> bool:
        """True if the active Python exists (does NOT verify packages each time)."""
        return Path(self.active_python).exists()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _load_saved_python(self) -> Optional[str]:
        try:
            data = json.loads(ENV_CONFIG.read_text(encoding="utf-8"))
            return data.get(self.venv_name)
        except Exception:
            return None

    def save_active_python(self, python_path: str) -> None:
        """Persist the user's chosen Python for this tool."""
        VENVS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(ENV_CONFIG.read_text(encoding="utf-8")) if ENV_CONFIG.exists() else {}
        except Exception:
            data = {}
        data[self.venv_name] = python_path
        ENV_CONFIG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def clear_saved_python(self) -> None:
        """Remove saved preference so the next run re-detects."""
        try:
            data = json.loads(ENV_CONFIG.read_text(encoding="utf-8"))
            data.pop(self.venv_name, None)
            ENV_CONFIG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Environment detection
    # ------------------------------------------------------------------

    def detect_envs(self) -> List[dict]:
        """
        Return all discovered environments, each annotated with whether
        it already has the required packages.
        Result format:
          { "label": str, "python": str, "source": str, "has_packages": bool }
        """
        candidates = scan_candidate_envs()
        results = []
        for c in candidates:
            has = _verify_imports(c["python"], self.check_imports)
            results.append({**c, "has_packages": has})
        return results

    def verify_env(self, python_path: str) -> bool:
        return _verify_imports(python_path, self.check_imports)

    # ------------------------------------------------------------------
    # Managed venv creation
    # ------------------------------------------------------------------

    def _resolve_requirements(self) -> Path:
        if Path(self.requirements_file).is_absolute():
            return Path(self.requirements_file)
        tool_module = sys.modules.get(self.__class__.__module__)
        if tool_module and getattr(tool_module, "__file__", None):
            return Path(tool_module.__file__).parent / self.requirements_file
        return PROJECT_ROOT / self.requirements_file

    def setup_venv(self, log_cb=print) -> None:
        """Create managed venv and install requirements. Blocks."""
        req_path = self._resolve_requirements()
        if not req_path.exists():
            raise FileNotFoundError(f"找不到 requirements 檔案: {req_path}")

        log_cb(f"[環境] 建立虛擬環境: {self.venv_dir}")
        VENVS_DIR.mkdir(parents=True, exist_ok=True)
        _venv.create(str(self.venv_dir), with_pip=True, clear=False)

        log_cb("[環境] 升級 pip...")
        subprocess.run(
            [self.venv_python, "-m", "pip", "install", "--upgrade", "pip"],
            check=True, stdout=subprocess.DEVNULL,
        )
        log_cb(f"[環境] 安裝套件 ({req_path.name})...")
        subprocess.run(
            [self.venv_python, "-m", "pip", "install", "-r", str(req_path)],
            check=True,
        )
        log_cb("[環境] 完成！")
        # Auto-save so next run skips detection
        self.save_active_python(self.venv_python)

    def setup_conda_env(self, env_name: str = "", python_version: str = "3.10",
                        log_cb=print) -> None:
        """Create a conda env and install requirements. Blocks.

        env_name: conda environment name (defaults to "<venv_name>-env")
        """
        import json as _json

        if not env_name:
            env_name = f"{self.venv_name}-env"

        req_path = self._resolve_requirements()
        if not req_path.exists():
            raise FileNotFoundError(f"找不到 requirements 檔案: {req_path}")

        def _stream(cmd):
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            for line in proc.stdout:
                log_cb(line.rstrip())
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"指令失敗 (exit {proc.returncode}): {' '.join(cmd)}")

        log_cb(f"[conda] 建立環境: {env_name}  (python={python_version})")
        _stream(["conda", "create", "-n", env_name, f"python={python_version}", "-y"])

        log_cb(f"[conda] 安裝套件 ({req_path.name})...")
        _stream(["conda", "run", "--no-capture-output", "-n", env_name,
                 "pip", "install", "-r", str(req_path)])

        # Locate the new env's python
        log_cb("[conda] 尋找新環境路徑...")
        r = subprocess.run(
            ["conda", "env", "list", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        python_path = None
        for env_path in _json.loads(r.stdout).get("envs", []):
            if Path(env_path).name == env_name:
                p = _python_in_dir(Path(env_path))
                if p:
                    python_path = p
                    break

        if not python_path:
            raise RuntimeError(f"找不到新建環境的 Python，環境名稱: {env_name}")

        log_cb(f"[conda] 完成！Python: {python_path}")
        self.save_active_python(python_path)

    # ------------------------------------------------------------------
    # Subprocess execution
    # ------------------------------------------------------------------

    def popen_runner(self, runner_path: str, extra_args: list, **kwargs) -> subprocess.Popen:
        """Spawn runner.py using the active Python. Raises if not ready."""
        python = self.active_python
        if not Path(python).exists():
            raise RuntimeError(f"環境尚未設定，請先選擇或建立環境。工具: {self.name}")
        cmd = [python, runner_path] + extra_args
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, **kwargs,
        )

    # ------------------------------------------------------------------
    # CLI
    # ------------------------------------------------------------------

    def run_cli(self, args) -> None:
        if not self.is_ready:
            print(f"[{self.display_name}] 正在尋找可用環境...")
            envs = self.detect_envs()
            ready = [e for e in envs if e["has_packages"]]
            if ready:
                chosen = ready[0]
                print(f"[{self.display_name}] 自動選用: {chosen['label']}")
                self.save_active_python(chosen["python"])
            else:
                print(f"[{self.display_name}] 未找到合適環境，正在建立新環境...")
                self.setup_venv(log_cb=print)

        runner = self._runner_path()
        proc = self.popen_runner(str(runner), self._runner_args(args))
        for raw in proc.stdout:
            line = raw.rstrip()
            if line.startswith(PREFIX_LOG):
                print(line[len(PREFIX_LOG):])
            elif line.startswith(PREFIX_TEXT):
                print(line[len(PREFIX_TEXT):])
            elif line.startswith(PREFIX_PROGRESS):
                parts = line[len(PREFIX_PROGRESS):].split(",", 2)
                try:
                    msg = parts[2] if len(parts) > 2 else ""
                    print(f"\r[Stage {parts[0]}] {float(parts[1]):.0f}%  {msg}", end="", flush=True)
                except (ValueError, IndexError):
                    pass
            elif line.startswith(PREFIX_DONE):
                print(f"\n[完成] {line[len(PREFIX_DONE):]}")
            elif line.startswith(PREFIX_ERROR):
                print(f"\n[錯誤] {line[len(PREFIX_ERROR):]}", file=sys.stderr)
        proc.wait()

    @abstractmethod
    def _runner_path(self) -> Path: ...

    @abstractmethod
    def _runner_args(self, args) -> list: ...

    # ------------------------------------------------------------------
    # GUI
    # ------------------------------------------------------------------

    def get_ui_panel(self, parent) -> "tk.Widget":
        from core.isolated_panel import IsolatedPanel
        return IsolatedPanel(parent, self)
