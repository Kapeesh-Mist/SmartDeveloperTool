"""CLI integration tests for `smartdevtool docker` commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from smartdevtool.cli import app
from smartdevtool.manifest import ManifestManager

runner = CliRunner()


def test_cli_docker_build_generates_dockerfile(tmp_path: Path):
    """Test `smartdevtool docker build` generates a tailored Dockerfile."""
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")

    # Record some dependencies in manifest
    mgr = ManifestManager(tmp_path)
    mgr.record_dependencies(
        imports=["requests"],
        distribution_map={"requests": "requests"},
        pinned_dependencies=["requests==2.31.0"],
    )

    result = runner.invoke(
        app,
        ["docker", "build", str(tmp_path), "--no-llm", "-y"],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "Dockerfile").exists()
    content = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:" in content
    assert "COPY requirements.txt ." in content


def test_cli_docker_sync(tmp_path: Path):
    """Test `smartdevtool docker sync` in non-watch mode."""
    (tmp_path / "main.py").write_text("API_VAL = 1", encoding="utf-8")

    result = runner.invoke(
        app,
        ["docker", "sync", str(tmp_path), "--no-llm", "-y"],
    )
    assert result.exit_code == 0, result.output
    # Either says in sync or reports drift
    assert "sync" in result.output.lower() or "drift" in result.output.lower()
