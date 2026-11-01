"""Tests for DockerBuilder and SyncAgent with graceful degradation when Docker is unavailable."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from smartdevtool.docker.build import DockerBuilder, docker_available
from smartdevtool.docker.sync_agent import SyncAgent
from smartdevtool.manifest import ManifestManager


def test_docker_available_callable():
    """Verify docker_available() returns a boolean without throwing exceptions."""
    result = docker_available()
    assert isinstance(result, bool)


def test_docker_builder_missing_cli(tmp_path: Path):
    """Verify DockerBuilder reports clean failure when docker CLI is not found."""
    builder = DockerBuilder(docker_bin="nonexistent_docker_binary_xyz")
    success, msg = builder.build(tag="test:latest", context_dir=tmp_path)
    assert success is False
    assert "not installed" in msg.lower() or "not found" in msg.lower()


def test_sync_agent_in_sync(tmp_path: Path):
    """Verify SyncAgent detects in-sync state when current hash equals recorded hash."""
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")

    mgr = ManifestManager(tmp_path)
    agent = SyncAgent(project_root=tmp_path, auto_yes=True)

    # Record current hash as last build hash
    current_h, _ = agent.change_detector.compute_fingerprint()
    mgr.record_docker(
        base_image="python:3.11-slim",
        dockerfile_path="Dockerfile",
        image_tag="test:latest",
        last_build_hash=current_h,
    )

    in_sync, msg = agent.sync_once()
    assert in_sync is True
    assert "in sync" in msg.lower()


def test_sync_agent_drift_rebuild_mocked(tmp_path: Path):
    """Verify SyncAgent rebuild flow on drift with a mocked builder."""
    (tmp_path / "app.py").write_text("print('version 1')", encoding="utf-8")

    agent = SyncAgent(project_root=tmp_path, image_tag="test:v1", auto_yes=True)
    # Mock builder to simulate successful build without requiring real daemon
    agent.builder.build = MagicMock(return_value=(True, "Successfully built 1234abcd"))

    with patch("smartdevtool.docker.sync_agent.docker_available", return_value=True):
        success, msg = agent.sync_once()

    assert success is True
    assert agent.builder.build.called
    assert (tmp_path / "Dockerfile").exists()

    # Confirm manifest recorded the new build
    manifest = agent.manifest_mgr.load()
    assert manifest.docker.image_tag == "test:v1"
    assert manifest.docker.last_build_hash is not None


def test_real_docker_build_if_daemon_present(tmp_path: Path):
    """If real Docker daemon is running, execute a real build; otherwise skip cleanly."""
    if not docker_available():
        pytest.skip("Docker daemon is not running. Skipping live Docker build test.")

    (tmp_path / "Dockerfile").write_text(
        "FROM alpine:latest\nCMD [\"echo\", \"smartdevtool\"]\n", encoding="utf-8"
    )
    builder = DockerBuilder()
    success, output = builder.build(tag="sdt-test:latest", context_dir=tmp_path)
    assert success is True, output
