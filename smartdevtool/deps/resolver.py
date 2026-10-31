"""Subprocess wrapper for the real `pip-compile` backtracking dependency resolver.

Executes `pip-compile --quiet --no-header --strip-extras --resolver=backtracking --upgrade --output-file <out> <in>`.
The `--upgrade` flag is strictly required to prevent pre-existing output files from
silently dragging resolution toward stale pins.

Accurately distinguishes genuine multi-package version conflicts from unrelated
failures like nonexistent package names.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompileResult:
    """Outcome of a pip-compile execution."""

    success: bool
    returncode: int
    stdout: str
    stderr: str
    is_conflict: bool
    output_file: Path | None = None

    @property
    def combined_output(self) -> str:
        """Combined stdout and stderr text."""
        return f"{self.stdout}\n{self.stderr}".strip()


# Strings indicating an invalid / nonexistent package or network error, NOT a resolvable pin conflict.
# pip's traceback may include "ResolutionImpossible" even when a package doesn't exist,
# so these exclusions MUST be tested first.
NON_CONFLICT_EXCLUSIONS = [
    "no matching distribution found",
    "from versions: none",
    "could not find a version that satisfies",
    "not a valid package name",
    "invalid requirement",
]

# Markers indicating a genuine multi-package version incompatibility.
CONFLICT_MARKERS = [
    "conflicting dependencies",
    "cannot install",
    "resolutionimpossible",
    "incompatible with",
    "because these versions depend on",
]


def is_resolution_conflict(result: CompileResult) -> bool:
    """Distinguish a real multi-package version conflict from unrelated failures.

    Checks non-conflict exclusions FIRST before evaluating conflict markers.
    """
    if result.success:
        return False

    text = result.combined_output.lower()

    # Step 1: Check exclusions first!
    for exclusion in NON_CONFLICT_EXCLUSIONS:
        if exclusion in text:
            return False

    # Step 2: Check conflict markers
    for marker in CONFLICT_MARKERS:
        if marker in text:
            return True

    return False


class DependencyResolver:
    """Wraps the real pip-compile binary."""

    def __init__(self, python_executable: str | None = None) -> None:
        self.python_executable = python_executable or sys.executable

    def _get_pip_compile_cmd(self) -> list[str]:
        """Resolve command to execute pip-compile."""
        pip_compile_bin = shutil.which("pip-compile")
        if pip_compile_bin:
            return [pip_compile_bin]
        return [self.python_executable, "-m", "piptools", "compile"]

    def compile(
        self,
        input_file: Path | str,
        output_file: Path | str,
        extra_args: list[str] | None = None,
        timeout: float = 120.0,
    ) -> CompileResult:
        """Run pip-compile with backtracking and upgrade flags."""
        input_path = Path(input_file).resolve()
        output_path = Path(output_file).resolve()

        cmd = self._get_pip_compile_cmd() + [
            "--quiet",
            "--no-header",
            "--strip-extras",
            "--resolver=backtracking",
            "--upgrade",
            "--output-file",
            str(output_path),
            str(input_path),
        ]

        if extra_args:
            cmd.extend(extra_args)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            res = CompileResult(
                success=(proc.returncode == 0),
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                is_conflict=False,
                output_file=output_path if proc.returncode == 0 else None,
            )
            res.is_conflict = is_resolution_conflict(res)
            return res
        except subprocess.TimeoutExpired as exc:
            return CompileResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr=f"pip-compile timed out after {timeout} seconds: {exc}",
                is_conflict=False,
            )
        except Exception as exc:
            return CompileResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr=f"Failed to execute pip-compile: {exc}",
                is_conflict=False,
            )
