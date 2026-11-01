"""Unit tests for the Shared Core modules: config, ui, manifest, llm/client."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from smartdevtool import ui
from smartdevtool.config import Config
from smartdevtool.llm.client import LLMClient
from smartdevtool.manifest import ManifestManager


def test_config_env_dynamic_evaluation():
    """Verify that default_factory re-evaluates at instantiation time, not at import time."""
    old_val = os.environ.get("MAX_ITERS_DEPS")
    try:
        os.environ["MAX_ITERS_DEPS"] = "15"
        cfg = Config.load()
        assert cfg.max_iters_deps == 15

        os.environ["MAX_ITERS_DEPS"] = "42"
        cfg2 = Config.load()
        assert cfg2.max_iters_deps == 42

        # Explicit overrides take precedence
        cfg3 = Config.load(max_iters_deps=5)
        assert cfg3.max_iters_deps == 5
    finally:
        if old_val is not None:
            os.environ["MAX_ITERS_DEPS"] = old_val
        else:
            os.environ.pop("MAX_ITERS_DEPS", None)


def test_ui_helpers_smoke():
    """Verify rich helpers execute without raising exceptions."""
    ui.header("Test Header")
    ui.step("Processing step")
    ui.success("Operation completed")
    ui.warn("Potential issue")
    ui.error("An error occurred")
    ui.agent_attempt(1, 8, "Resolving conflict")
    assert ui.confirm("Continue?", auto_yes=True) is True
    ui.summary_panel("Summary", {"key1": "value1", "key2": 123})
    ui.summary_panel("List Summary", ["Item A", "Item B"])
    ui.summary_panel("Text Summary", "Simple text content")


def test_manifest_lifecycle(tmp_path: Path):
    """Verify ManifestManager saves and loads sections across all three domains."""
    manager = ManifestManager(project_root=tmp_path)
    manifest = manager.load()
    assert manifest.version == "0.1.0"
    assert manifest.dependencies.imports == []
    assert manifest.wrappers == []
    assert manifest.docker.base_image is None

    # Record dependencies
    manager.record_dependencies(
        imports=["requests", "rich"],
        distribution_map={"requests": "requests", "rich": "rich"},
        pinned_dependencies=["requests==2.31.0", "rich==13.7.1"],
        lockfile_path="requirements.txt",
    )

    # Record wrapper
    manager.record_wrapper(
        name="PetstoreSDK",
        source_type="curl",
        file_path="petstore.py",
        base_url="https://api.petstore.com",
        endpoints=["/pets", "/pets/{id}"],
        auth_type="api_key",
    )

    # Record docker
    manager.record_docker(
        base_image="python:3.11-slim",
        dockerfile_path="Dockerfile",
        image_tag="smartdevtool:latest",
        last_build_hash="abc123sha",
    )

    # Reload and assert everything is preserved
    reloaded = manager.load()
    assert reloaded.dependencies.imports == ["requests", "rich"]
    assert len(reloaded.wrappers) == 1
    assert reloaded.wrappers[0].name == "PetstoreSDK"
    assert reloaded.docker.base_image == "python:3.11-slim"


def test_llm_client_unavailable_fallback():
    """Verify LLMClient safely reports unavailable and does not raise on completions."""
    with patch.dict(os.environ, {"NVIDIA_API_KEY": ""}, clear=True):
        client = LLMClient(Config.load(nvidia_api_key=None, offline_mode=True))
        assert client.available is False
        assert client.provider is None
        assert client.complete("Hello") is None
        assert client.complete_json("system", "user") is None


def test_llm_client_extract_json():
    """Verify JSON parsing handles raw text and markdown code blocks."""
    client = LLMClient(Config.load(offline_mode=True))
    assert client._extract_json('{"key": "value"}') == {"key": "value"}
    assert client._extract_json('```json\n{"action": "unpin"}\n```') == {"action": "unpin"}
    assert client._extract_json("invalid json string") is None
