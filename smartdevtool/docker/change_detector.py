"""Change detector module using hashlib SHA-256 fingerprinting.

Computes a deterministic hash of the project source tree and lockfile,
comparing against the hash recorded at the last successful Docker build to detect drift.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

IGNORE_DIRS = {
    ".git",
    ".venv",
    ".clean_room_env",
    ".clean_room_env2",
    ".clean_room_env3",
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

IGNORE_EXTENSIONS = {".pyc", ".pyo", ".pyd", ".whl", ".tar.gz", ".zip"}


class ChangeDetector:
    """Computes source tree hashes and detects environment drift."""

    def __init__(self, project_root: Path | str = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def compute_fingerprint(
        self, lockfile_path: Path | str | None = None
    ) -> tuple[str, list[str]]:
        """Compute SHA-256 hash of all tracked source files and the dependency lockfile.

        Returns (hexdigest, list_of_tracked_relative_paths).
        """
        hasher = hashlib.sha256()
        tracked_files: list[str] = []

        if not self.project_root.exists():
            return hasher.hexdigest(), []

        file_paths: list[Path] = []

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in IGNORE_EXTENSIONS or file.startswith("."):
                    continue
                file_paths.append(Path(root) / file)

        # Sort file paths deterministically
        file_paths.sort()

        for fp in file_paths:
            try:
                rel_path = fp.relative_to(self.project_root).as_posix()
                tracked_files.append(rel_path)

                hasher.update(rel_path.encode("utf-8"))
                with open(fp, "rb") as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
            except Exception:
                continue

        # Include dependency lockfile if provided and exists
        if lockfile_path:
            lock_p = Path(lockfile_path).resolve()
            if lock_p.exists():
                hasher.update(b"__LOCKFILE__")
                try:
                    with open(lock_p, "rb") as f:
                        while chunk := f.read(65536):
                            hasher.update(chunk)
                except Exception:
                    pass

        return hasher.hexdigest(), tracked_files

    def detect_drift(
        self,
        last_build_hash: str | None,
        lockfile_path: Path | str | None = None,
    ) -> tuple[bool, str, list[str]]:
        """Determine if source code or dependencies have drifted from last build.

        Returns (is_drift, current_hash, tracked_files).
        """
        current_hash, tracked_files = self.compute_fingerprint(lockfile_path=lockfile_path)

        if last_build_hash is None:
            return True, current_hash, tracked_files

        is_drift = (current_hash != last_build_hash)
        return is_drift, current_hash, tracked_files
