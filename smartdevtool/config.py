"""Central configuration dataclass for SmartDevTool.

Values follow the precedence: CLI flag > env var > default.
Every environment-read default uses dataclasses.field(default_factory=...)
so that values are evaluated at instantiation time rather than at import time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """SmartDevTool runtime configuration."""

    # LLM Provider settings
    nvidia_api_key: str | None = field(
        default_factory=lambda: os.getenv("NVIDIA_API_KEY") or None
    )
    nvidia_base_url: str = field(
        default_factory=lambda: os.getenv(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
    )
    nvidia_model: str = field(
        default_factory=lambda: os.getenv(
            "NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"
        )
    )

    ollama_host: str = field(
        default_factory=lambda: os.getenv(
            "OLLAMA_HOST", "http://localhost:11434"
        )
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1")
    )

    # Agent iteration budgets
    max_iters_deps: int = field(
        default_factory=lambda: int(os.getenv("MAX_ITERS_DEPS", "8"))
    )
    max_iters_wrapper: int = field(
        default_factory=lambda: int(os.getenv("MAX_ITERS_WRAPPER", "6"))
    )

    # Runtime behavior
    offline_mode: bool = field(
        default_factory=lambda: os.getenv(
            "SMARTDEVTOOL_OFFLINE_MODE", "false"
        ).lower()
        in ("true", "1", "yes")
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("SMARTDEVTOOL_LOG_LEVEL", "INFO")
    )
    manifest_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("SMARTDEVTOOL_MANIFEST_DIR", ".smartdevtool")
        )
    )

    @classmethod
    def load(cls, **overrides) -> Config:
        """Instantiate Config, overriding any values provided directly (e.g. from CLI flags)."""
        valid_overrides = {k: v for k, v in overrides.items() if v is not None}
        return cls(**valid_overrides)
