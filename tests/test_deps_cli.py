"""CLI integration tests for `smartdevtool deps` commands via Typer CliRunner."""

from __future__ import annotations

from pathlib import Path
from typer.testing import CliRunner
from smartdevtool.cli import app

runner = CliRunner()


def test_cli_deps_scan(tmp_path: Path):
    """Test `smartdevtool deps scan` output."""
    (tmp_path / "app.py").write_text("import requests\nimport yaml\n", encoding="utf-8")

    result = runner.invoke(app, ["deps", "scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "requests" in result.output
    assert "yaml" in result.output


def test_cli_deps_install_dry_run(tmp_path: Path):
    """Test `smartdevtool deps install --dry-run --no-llm -y`."""
    (tmp_path / "main.py").write_text("import six\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "deps",
            "install",
            str(tmp_path),
            "--dry-run",
            "--no-llm",
            "-y",
            "-o",
            "test_reqs.txt",
        ],
    )
    assert result.exit_code == 0
    assert "Manifest updated" in result.output or "Dry Run" in result.output
    # Confirm lockfile was written
    lockfile = tmp_path / "test_reqs.txt"
    assert lockfile.exists()
    assert "six" in lockfile.read_text(encoding="utf-8")
