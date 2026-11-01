"""Dependency installer module.

Executes `pip install -r <lockfile>`, optionally into an isolated
virtual environment (.smartdevtool/venv) created via Python's stdlib `venv` module.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

from smartdevtool import ui


class DependencyInstaller:
    """Installs resolved dependencies from a lockfile."""

    def __init__(self, python_executable: str | None = None) -> None:
        self.python_executable = python_executable or sys.executable

    def create_venv(self, venv_dir: Path | str) -> Path:
        """Create an isolated virtual environment using stdlib venv."""
        target = Path(venv_dir).resolve()
        if not target.exists():
            ui.step(f"Creating isolated virtual environment at {target}...")
            venv.create(target, with_pip=True, clear=False)
        return target

    def _get_venv_pip(self, venv_dir: Path) -> str:
        """Locate pip executable within the target virtualenv."""
        if os.name == "nt":
            pip_path = venv_dir / "Scripts" / "pip.exe"
        else:
            pip_path = venv_dir / "bin" / "pip"

        if pip_path.exists():
            return str(pip_path)
        # Fallback to python -m pip inside venv
        if os.name == "nt":
            py_path = venv_dir / "Scripts" / "python.exe"
        else:
            py_path = venv_dir / "bin" / "python"
        return str(py_path)

    def install(
        self,
        lockfile_path: Path | str,
        venv_dir: Path | str | None = None,
        dry_run: bool = False,
    ) -> tuple[bool, str]:
        """Install dependencies from lockfile."""
        lockfile = Path(lockfile_path).resolve()
        if not lockfile.exists():
            return False, f"Lockfile not found: {lockfile}"

        if dry_run:
            with open(lockfile, encoding="utf-8") as f:
                content = f.read()
            ui.summary_panel(f"Dry Run: {lockfile.name}", content)
            return True, "Dry-run completed. No packages installed."

        if venv_dir:
            venv_path = self.create_venv(venv_dir)
            pip_bin = self._get_venv_pip(venv_path)
            cmd = [pip_bin, "install", "-r", str(lockfile)]
        else:
            cmd = [self.python_executable, "-m", "pip", "install", "-r", str(lockfile)]

        ui.step(f"Running: {' '.join(cmd)}")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            output = f"{proc.stdout}\n{proc.stderr}".strip()
            return proc.returncode == 0, output
        except Exception as exc:
            return False, f"Failed to execute pip install: {exc}"
