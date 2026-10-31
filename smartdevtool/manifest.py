"""Manifest management and schema dataclasses for SmartDevTool.

Persisted at `.smartdevtool/manifest.json`.
Reserves sections for all three features (dependencies, sources, wrappers, docker)
up front so no schema migration is required as features are added.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DependencySection:
    """Tracked dependency resolution metadata."""

    imports: list[str] = field(default_factory=list)
    distribution_map: dict[str, str] = field(default_factory=dict)
    pinned_dependencies: list[str] = field(default_factory=list)
    lockfile_path: str | None = None
    last_resolved_at: str | None = None


@dataclass
class SourcesSection:
    """Source code tree fingerprinting metadata."""

    source_files: list[str] = field(default_factory=list)
    tree_hash: str | None = None
    last_scanned_at: str | None = None


@dataclass
class WrapperMetadata:
    """Generated API wrapper metadata."""

    name: str
    source_type: str  # "curl", "postman", "har", "doc"
    file_path: str
    base_url: str
    endpoints: list[str] = field(default_factory=list)
    auth_type: str = "none"
    generated_at: str | None = None


@dataclass
class DockerSection:
    """Docker image and build synchronization metadata."""

    base_image: str | None = None
    dockerfile_path: str | None = None
    image_tag: str | None = None
    last_build_hash: str | None = None
    last_built_at: str | None = None


@dataclass
class Manifest:
    """Root manifest tree schema."""

    version: str = "0.1.0"
    dependencies: DependencySection = field(default_factory=DependencySection)
    sources: SourcesSection = field(default_factory=SourcesSection)
    wrappers: list[WrapperMetadata] = field(default_factory=list)
    docker: DockerSection = field(default_factory=DockerSection)

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Construct Manifest tree from dictionary."""
        deps_data = data.get("dependencies", {})
        sources_data = data.get("sources", {})
        wrappers_data = data.get("wrappers", [])
        docker_data = data.get("docker", {})

        return cls(
            version=data.get("version", "0.1.0"),
            dependencies=DependencySection(
                imports=deps_data.get("imports", []),
                distribution_map=deps_data.get("distribution_map", {}),
                pinned_dependencies=deps_data.get("pinned_dependencies", []),
                lockfile_path=deps_data.get("lockfile_path"),
                last_resolved_at=deps_data.get("last_resolved_at"),
            ),
            sources=SourcesSection(
                source_files=sources_data.get("source_files", []),
                tree_hash=sources_data.get("tree_hash"),
                last_scanned_at=sources_data.get("last_scanned_at"),
            ),
            wrappers=[
                WrapperMetadata(
                    name=w.get("name", ""),
                    source_type=w.get("source_type", ""),
                    file_path=w.get("file_path", ""),
                    base_url=w.get("base_url", ""),
                    endpoints=w.get("endpoints", []),
                    auth_type=w.get("auth_type", "none"),
                    generated_at=w.get("generated_at"),
                )
                for w in wrappers_data
            ],
            docker=DockerSection(
                base_image=docker_data.get("base_image"),
                dockerfile_path=docker_data.get("dockerfile_path"),
                image_tag=docker_data.get("image_tag"),
                last_build_hash=docker_data.get("last_build_hash"),
                last_built_at=docker_data.get("last_built_at"),
            ),
        )


class ManifestManager:
    """Manages reading and persisting `.smartdevtool/manifest.json`."""

    DEFAULT_FILENAME = "manifest.json"

    def __init__(self, project_root: Path | str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.manifest_dir = self.project_root / ".smartdevtool"
        self.manifest_path = self.manifest_dir / self.DEFAULT_FILENAME

    def load(self) -> Manifest:
        """Load manifest from disk or return default empty tree if missing."""
        if not self.manifest_path.exists():
            return Manifest()

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Manifest.from_dict(data)
        except Exception:
            return Manifest()

    def save(self, manifest: Manifest) -> Path:
        """Persist manifest tree to `.smartdevtool/manifest.json`."""
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)
        return self.manifest_path

    def record_dependencies(
        self,
        imports: list[str],
        distribution_map: dict[str, str],
        pinned_dependencies: list[str],
        lockfile_path: str | None = None,
    ) -> Manifest:
        """Update and save dependencies section."""
        manifest = self.load()
        manifest.dependencies = DependencySection(
            imports=sorted(list(set(imports))),
            distribution_map=distribution_map,
            pinned_dependencies=pinned_dependencies,
            lockfile_path=lockfile_path,
            last_resolved_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save(manifest)
        return manifest

    def record_wrapper(
        self,
        name: str,
        source_type: str,
        file_path: str,
        base_url: str,
        endpoints: list[str],
        auth_type: str = "none",
    ) -> Manifest:
        """Append or update a wrapper record and save manifest."""
        manifest = self.load()
        existing = next((w for w in manifest.wrappers if w.file_path == file_path), None)
        record = WrapperMetadata(
            name=name,
            source_type=source_type,
            file_path=file_path,
            base_url=base_url,
            endpoints=endpoints,
            auth_type=auth_type,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        if existing:
            manifest.wrappers.remove(existing)
        manifest.wrappers.append(record)
        self.save(manifest)
        return manifest

    def record_docker(
        self,
        base_image: str | None,
        dockerfile_path: str | None,
        image_tag: str | None,
        last_build_hash: str | None,
    ) -> Manifest:
        """Update and save docker section."""
        manifest = self.load()
        manifest.docker = DockerSection(
            base_image=base_image,
            dockerfile_path=dockerfile_path,
            image_tag=image_tag,
            last_build_hash=last_build_hash,
            last_built_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save(manifest)
        return manifest
