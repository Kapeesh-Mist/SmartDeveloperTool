"""Unit tests for Dockerfile generation, layer caching, and secrets discipline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from smartdevtool.docker.dockerfile_gen import DockerfileGenerator
from smartdevtool.llm.client import LLMClient


def test_dockerfile_layer_caching_and_ordering():
    """Verify layer-cache friendly ordering: requirements copied and installed BEFORE app code."""
    generator = DockerfileGenerator()
    content = generator.generate(
        dependencies=["requests==2.31.0", "rich==13.7.1"],
        requirements_file="requirements.txt",
        env_vars=["API_KEY", "DATABASE_URL"],
        expose_port=8000,
    )

    # Requirements COPY must precede COPY . .
    copy_req_idx = content.find("COPY requirements.txt .")
    run_pip_idx = content.find("RUN pip install")
    copy_app_idx = content.find("COPY . .")

    assert copy_req_idx != -1
    assert run_pip_idx != -1
    assert copy_app_idx != -1

    assert copy_req_idx < run_pip_idx < copy_app_idx, "Requirements must be installed before copying app code"


def test_dockerfile_secrets_discipline():
    """Secrets discipline: ENV declarations declare variable NAMES only, never real secrets."""
    generator = DockerfileGenerator()
    content = generator.generate(
        dependencies=[],
        env_vars=["SECRET_TOKEN", "STRIPE_KEY"],
    )

    assert 'ENV SECRET_TOKEN=""' in content
    assert 'ENV STRIPE_KEY=""' in content
    # Ensure no actual secret strings are present
    assert "sk_" not in content
    assert "bearer" not in content.lower()


def test_dockerfile_base_image_heuristic():
    """Heuristic base image selection: PyTorch triggers CUDA runtime, standard packages trigger slim."""
    generator = DockerfileGenerator()

    # Standard python packages
    std_img, _, _ = generator.select_base_image(["requests", "rich", "pydantic"])
    assert "python:" in std_img
    assert "slim" in std_img

    # ML packages
    ml_img, pkgs, _ = generator.select_base_image(["torch>=2.0.0", "numpy"])
    assert "pytorch" in ml_img or "cuda" in ml_img


def test_dockerfile_base_image_llm():
    """Test LLM-based base image selection with scripted mock LLMClient."""
    fake_llm = MagicMock(spec=LLMClient)
    fake_llm.available = True
    fake_llm.complete_json.return_value = {
        "base_image": "python:3.12-alpine",
        "system_packages": ["gcc", "musl-dev"],
        "reasoning": "Alpine recommended for minimal image size",
    }

    generator = DockerfileGenerator(llm_client=fake_llm)
    img, sys_pkgs, _ = generator.select_base_image(["httpx"])

    assert img == "python:3.12-alpine"
    assert "gcc" in sys_pkgs
    assert fake_llm.complete_json.called
