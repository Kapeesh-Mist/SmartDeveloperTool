"""Subprocess wrapper around the real `docker` CLI.

Avoids third-party docker SDK dependencies and Docker Engine API version coupling.
Provides graceful detection and messaging when Docker is not installed or the daemon is not running.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def docker_available() -> bool:
    """Check whether the docker CLI binary is present and reachable."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False

    try:
        # Verify daemon is running with a quick ping
        res = subprocess.run(
            [docker_bin, "info"],
            capture_output=True,
            timeout=2.0,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


class DockerBuilder:
    """Builds Docker images using the docker CLI."""

    def __init__(self, docker_bin: str | None = None) -> None:
        self.docker_bin = docker_bin or shutil.which("docker") or "docker"

    def build(
        self,
        tag: str,
        context_dir: Path | str = ".",
        dockerfile: Path | str | None = None,
        extra_args: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Execute `docker build -t <tag> .`."""
        if not shutil.which(self.docker_bin):
            return False, "Docker CLI is not installed or not found on PATH."

        context_path = Path(context_dir).resolve()
        cmd = [self.docker_bin, "build", "-t", tag]

        if dockerfile:
            df_path = Path(dockerfile).resolve()
            cmd.extend(["-f", str(df_path)])

        if extra_args:
            cmd.extend(extra_args)

        cmd.append(str(context_path))

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
            return False, f"Failed to execute docker build: {exc}"
