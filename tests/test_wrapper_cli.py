"""CLI integration tests for `smartdevtool wrapper` command covering all 4 input flags."""

from __future__ import annotations

import ast
from pathlib import Path

from typer.testing import CliRunner

from smartdevtool.cli import app
from smartdevtool.manifest import ManifestManager

runner = CliRunner()


def test_cli_wrapper_curl_flag(tmp_path: Path):
    """Test `smartdevtool wrapper --curl` generates valid SDK and records manifest."""
    curl_cmd = 'curl -X GET "https://api.example.com/v1/search?q=test" -H "Authorization: Bearer token"'
    result = runner.invoke(
        app,
        [
            "wrapper",
            "--curl",
            curl_cmd,
            "--output-dir",
            str(tmp_path),
            "--name",
            "SearchService",
            "--no-validate",
            "-y",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Generated Python SDK client saved to" in result.output

    # Check generated SDK file exists and passes AST parse
    sdk_file = tmp_path / "searchserviceclient_sdk.py"
    assert sdk_file.exists()
    content = sdk_file.read_text(encoding="utf-8")
    assert ast.parse(content) is not None
    assert "class SearchServiceClient" in content

    # Check manifest was recorded
    mgr = ManifestManager(tmp_path)
    manifest = mgr.load()
    assert len(manifest.wrappers) >= 1
    assert any(w.name == "SearchServiceClient" for w in manifest.wrappers)


def test_cli_wrapper_postman_flag(tmp_path: Path):
    """Test `smartdevtool wrapper --postman` flag."""
    col_path = Path("examples/sample_postman_collection.json")
    result = runner.invoke(
        app,
        [
            "wrapper",
            "--postman",
            str(col_path),
            "--output-dir",
            str(tmp_path),
            "--name",
            "PostmanService",
            "--no-validate",
            "-y",
        ],
    )
    assert result.exit_code == 0, result.output
    sdk_file = tmp_path / "postmanserviceclient_sdk.py"
    assert sdk_file.exists()
    assert ast.parse(sdk_file.read_text(encoding="utf-8")) is not None


def test_cli_wrapper_har_flag(tmp_path: Path):
    """Test `smartdevtool wrapper --har` flag."""
    har_path = Path("examples/sample_network_capture.har")
    result = runner.invoke(
        app,
        [
            "wrapper",
            "--har",
            str(har_path),
            "--output-dir",
            str(tmp_path),
            "--name",
            "HarService",
            "--no-validate",
            "-y",
        ],
    )
    assert result.exit_code == 0, result.output
    sdk_file = tmp_path / "harserviceclient_sdk.py"
    assert sdk_file.exists()
    assert ast.parse(sdk_file.read_text(encoding="utf-8")) is not None


def test_cli_wrapper_doc_flag(tmp_path: Path):
    """Test `smartdevtool wrapper --doc` flag."""
    doc_path = Path("examples/sample_openapi.json")
    result = runner.invoke(
        app,
        [
            "wrapper",
            "--doc",
            str(doc_path),
            "--output-dir",
            str(tmp_path),
            "--name",
            "DocService",
            "--no-validate",
            "-y",
        ],
    )
    assert result.exit_code == 0, result.output
    sdk_file = tmp_path / "docserviceclient_sdk.py"
    assert sdk_file.exists()
    assert ast.parse(sdk_file.read_text(encoding="utf-8")) is not None
