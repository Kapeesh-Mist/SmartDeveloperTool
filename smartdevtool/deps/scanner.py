"""AST-based import scanner for Python projects.

Scans all Python files using Python's `ast` module (never regex).
Filters out standard library modules, local project modules/packages (including
implicit namespace directories without __init__.py), and common ignore directories.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".venv",
    ".clean_room_env",
    "venv",
    "env",
    "__pycache__",
    ".smartdevtool",
    "dist",
    "build",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
}


class ImportScanner:
    """Scans project source files using AST to extract third-party import dependencies."""

    def __init__(self, project_root: Path | str = ".", ignore_dirs: set[str] | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.ignore_dirs = ignore_dirs or set(DEFAULT_IGNORE_DIRS)
        self.stdlib_names = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()

    def _get_local_module_names(self) -> set[str]:
        """Detect local modules and packages in the project tree to avoid false external imports.

        Includes top-level .py files, directories containing Python files, and their immediate
        submodules/subpackages (handling non-package-relative imports in legacy code).
        """
        local_names: set[str] = set()

        if not self.project_root.exists():
            return local_names

        for item in self.project_root.iterdir():
            if item.name in self.ignore_dirs or item.name.startswith("."):
                continue

            if item.is_file() and item.suffix == ".py":
                local_names.add(item.stem)
            elif item.is_dir():
                has_py = any(item.glob("**/*.py"))
                if has_py:
                    local_names.add(item.name)
                    # Also register internal subpackages/submodules
                    for sub in item.iterdir():
                        if sub.name.startswith((".", "__")):
                            continue
                        if sub.is_file() and sub.suffix == ".py":
                            local_names.add(sub.stem)
                        elif sub.is_dir() and any(sub.glob("**/*.py")):
                            local_names.add(sub.name)

        return local_names

    def scan(self) -> set[str]:
        """Walk the project tree and extract all third-party imported module names."""
        external_imports: set[str] = set()
        local_names = self._get_local_module_names()

        if not self.project_root.exists():
            return external_imports

        for root, dirs, files in os.walk(self.project_root):
            # Modify dirs in-place to avoid descending into ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs and not d.startswith(".")]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = Path(root) / file
                try:
                    with open(file_path, encoding="utf-8-sig", errors="replace") as f:
                        source = f.read()
                    tree = ast.parse(source, filename=str(file_path))
                except Exception:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            root_pkg = alias.name.split(".")[0]
                            if root_pkg and self._is_external(root_pkg, local_names):
                                external_imports.add(root_pkg)
                    elif isinstance(node, ast.ImportFrom):
                        # Skip relative imports (level > 0)
                        if node.level > 0 or not node.module:
                            continue
                        root_pkg = node.module.split(".")[0]
                        if root_pkg and self._is_external(root_pkg, local_names):
                            external_imports.add(root_pkg)

        return external_imports

    def _is_external(self, pkg_name: str, local_names: set[str]) -> bool:
        """Check whether a package is third-party."""
        if not pkg_name or pkg_name == "__future__":
            return False
        if pkg_name in self.stdlib_names:
            return False
        if pkg_name in local_names:
            return False
        return True
