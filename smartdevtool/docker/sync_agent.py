"""SyncAgent module for automated Docker environment synchronization.

Uses `watchdog` for file watching and ChangeDetector for SHA-256 drift calculation.
Explains drift in developer language via LLM or deterministic summary.
Requires ONE human confirmation before building.
Strict Scope Discipline: only touches Dockerfile and image tag; never modifies application source.
"""

from __future__ import annotations

import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from smartdevtool import ui
from smartdevtool.docker.build import DockerBuilder, docker_available
from smartdevtool.docker.change_detector import IGNORE_DIRS, ChangeDetector
from smartdevtool.docker.dockerfile_gen import DockerfileGenerator
from smartdevtool.llm.client import LLMClient
from smartdevtool.llm.prompts import (
    DOCKER_SYNC_EXPLAIN_SYSTEM_PROMPT,
    DOCKER_SYNC_EXPLAIN_USER_TEMPLATE,
)
from smartdevtool.manifest import ManifestManager


class SyncAgent:
    """Monitors environment drift and coordinates Docker rebuilds."""

    def __init__(
        self,
        project_root: Path | str = ".",
        image_tag: str = "smartdevtool:latest",
        llm_client: LLMClient | None = None,
        auto_yes: bool = False,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.image_tag = image_tag
        self.llm_client = llm_client
        self.auto_yes = auto_yes
        self.change_detector = ChangeDetector(self.project_root)
        self.manifest_mgr = ManifestManager(self.project_root)
        self.builder = DockerBuilder()
        self.dockerfile_gen = DockerfileGenerator(self.llm_client)

    def sync_once(self) -> tuple[bool, str]:
        """Perform a single drift detection and rebuild check."""
        manifest = self.manifest_mgr.load()
        last_hash = manifest.docker.last_build_hash
        lockfile = manifest.dependencies.lockfile_path or (self.project_root / "requirements.txt")

        is_drift, current_hash, tracked_files = self.change_detector.detect_drift(
            last_build_hash=last_hash,
            lockfile_path=lockfile,
        )

        if not is_drift:
            ui.success("Docker build is in sync with codebase (no drift detected).")
            return True, "In sync"

        ui.header("Docker Drift Detected")
        ui.step(f"Detected changes across {len(tracked_files)} tracked source files.")

        # Explain change
        explanation = self._explain_drift(tracked_files, last_hash)
        ui.summary_panel("Rebuild Plan", explanation)

        # ONE human confirmation
        if not ui.confirm(f"Rebuild Docker image '{self.image_tag}'?", default=True, auto_yes=self.auto_yes):
            ui.warn("Rebuild skipped by user.")
            return True, "Rebuild skipped"

        # Check docker availability
        if not docker_available():
            msg = "Docker daemon is not reachable. Cannot complete image rebuild."
            ui.warn(msg)
            return False, msg

        # Generate / update Dockerfile
        deps = manifest.dependencies.pinned_dependencies or []
        req_file = Path(lockfile).name if Path(lockfile).exists() else "requirements.txt"
        df_path = self.project_root / "Dockerfile"

        if not df_path.exists():
            ui.step("Generating Dockerfile...")
            self.dockerfile_gen.write(
                output_path=df_path,
                dependencies=deps,
                requirements_file=req_file,
            )

        # Rebuild
        ui.step(f"Building Docker image {self.image_tag}...")
        success, build_log = self.builder.build(
            tag=self.image_tag,
            context_dir=self.project_root,
            dockerfile=df_path,
        )

        if success:
            # Record build in manifest
            self.manifest_mgr.record_docker(
                base_image=None,
                dockerfile_path="Dockerfile",
                image_tag=self.image_tag,
                last_build_hash=current_hash,
            )
            ui.success(f"Docker image {self.image_tag} successfully built and recorded!")
            return True, "Rebuild succeeded"
        else:
            ui.error(f"Docker build failed:\n{build_log[:500]}")
            return False, f"Build failed: {build_log[:300]}"

    def _explain_drift(self, files: list[str], last_hash: str | None) -> str:
        """Generate human or LLM explanation of drift."""
        if self.llm_client and self.llm_client.available:
            prompt = DOCKER_SYNC_EXPLAIN_USER_TEMPLATE.format(
                changed_files="\n".join(files[:20]),
                dep_changes="Requirements or source files updated",
            )
            data = self.llm_client.complete_json(
                system_prompt=DOCKER_SYNC_EXPLAIN_SYSTEM_PROMPT,
                user_prompt=prompt,
            )
            if data and isinstance(data, dict) and "summary" in data:
                return data["summary"]

        if last_hash is None:
            return "Initial build required: No previous build recorded in manifest."
        return f"Codebase has drifted from previous recorded build (hash: {last_hash[:8]})."

    def watch(self, debounce_seconds: float = 2.0) -> None:
        """Watch filesystem for changes and trigger sync on drift."""
        agent = self

        class ChangeHandler(FileSystemEventHandler):
            def __init__(self) -> None:
                self.last_triggered = 0.0

            def on_any_event(self, event: FileSystemEvent) -> None:
                if event.is_directory:
                    return

                # Ignore directories
                path = Path(event.src_path)
                if any(part in IGNORE_DIRS or part.startswith(".") for part in path.parts):
                    return

                now = time.time()
                if now - self.last_triggered < debounce_seconds:
                    return
                self.last_triggered = now

                ui.step(f"Change detected on {path.name}. Checking environment drift...")
                agent.sync_once()

        observer = Observer()
        observer.schedule(ChangeHandler(), str(self.project_root), recursive=True)
        observer.start()
        ui.header(f"Watching {self.project_root} for changes... (Press Ctrl+C to stop)")

        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
