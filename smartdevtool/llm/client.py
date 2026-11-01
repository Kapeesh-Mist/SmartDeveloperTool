"""LLM client implementation using the OpenAI Python SDK transport.

Implements the provider chain in strict order:
1. NVIDIA NIM (if NVIDIA_API_KEY is set)
2. Local Ollama (if reachable at OLLAMA_HOST via GET /api/tags)
3. None (llm_client.available is False, degrading to deterministic heuristics)

All completion methods are fully exception-guarded and never raise.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from openai import OpenAI

from smartdevtool.config import Config


class LLMClient:
    """Thin OpenAI-compatible transport for NVIDIA NIM and Ollama with safe degradation."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()
        self.provider: str | None = None
        self.model: str | None = None
        self.available: bool = False
        self._client: OpenAI | None = None

        self._initialize_provider()

    def _initialize_provider(self) -> None:
        """Evaluate provider chain in strict order."""
        if self.config.offline_mode:
            self.available = False
            self.provider = None
            return

        # 1. NVIDIA NIM
        if self.config.nvidia_api_key and self.config.nvidia_api_key.strip():
            self.provider = "nvidia"
            self.model = self.config.nvidia_model
            self.available = True
            self._client = OpenAI(
                base_url=self.config.nvidia_base_url,
                api_key=self.config.nvidia_api_key.strip(),
                timeout=15.0,
            )
            return

        # 2. Local Ollama (quick GET /api/tags check)
        ollama_host = self.config.ollama_host.rstrip("/")
        try:
            resp = httpx.get(f"{ollama_host}/api/tags", timeout=1.0)
            if resp.status_code == 200:
                self.provider = "ollama"
                self.model = self.config.ollama_model
                self.available = True
                self._client = OpenAI(
                    base_url=f"{ollama_host}/v1",
                    api_key="ollama",
                    timeout=30.0,
                )
                return
        except Exception:
            pass

        # 3. None - fallback
        self.provider = None
        self.model = None
        self.available = False
        self._client = None

    def complete(self, prompt: str, system_prompt: str | None = None) -> str | None:
        """Generate text completion. Returns None on any failure, never raises."""
        if not self.available or self._client is None or not self.model:
            return None

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.1,
            )
            return response.choices[0].message.content
        except Exception:
            return None

    def complete_json(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any] | None:
        """Generate structured JSON completion. Returns None on any failure, never raises."""
        if not self.available or self._client is None or not self.model:
            return None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # Try requesting JSON object response
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            return self._extract_json(raw)
        except Exception:
            # Retry without response_format if provider doesn't support json_object mode
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=0.1,
                )
                raw = response.choices[0].message.content or ""
                return self._extract_json(raw)
            except Exception:
                return None

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any] | None:
        """Safely parse JSON from raw completion, handling markdown fences if present."""
        text = raw.strip()
        if not text:
            return None

        # Direct JSON parse attempt
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # Extract from ```json ... ``` code fence
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        return None
