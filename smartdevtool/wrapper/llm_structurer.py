"""LLM-assisted API structurer for unstructured or prose-only documentation.

ESCALATION ONLY: Invoked only when deterministic parsers yield zero endpoints.
Must return None cleanly (never raise) if the LLM is unavailable or its response is unusable.
"""

from __future__ import annotations

from typing import Any

from smartdevtool.llm.client import LLMClient
from smartdevtool.llm.prompts import (
    WRAPPER_STRUCTURER_SYSTEM_PROMPT,
    WRAPPER_STRUCTURER_USER_TEMPLATE,
)
from smartdevtool.wrapper.spec import AuthInfo, EndpointDef, EndpointSpec, ParamSpec


class LLMStructurer:
    """Extracts structured EndpointSpec from prose text when deterministic parsers find nothing."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def structure(self, raw_text: str) -> EndpointSpec | None:
        """Query LLM to extract structured endpoints from prose. Returns None on failure."""
        if not self.llm_client or not self.llm_client.available:
            return None

        prompt = WRAPPER_STRUCTURER_USER_TEMPLATE.format(raw_input=raw_text[:3000])
        try:
            data = self.llm_client.complete_json(
                system_prompt=WRAPPER_STRUCTURER_SYSTEM_PROMPT,
                user_prompt=prompt,
            )
            if not data or not isinstance(data, dict):
                return None

            return self._build_spec_from_dict(data)
        except Exception:
            return None

    def _build_spec_from_dict(self, data: dict[str, Any]) -> EndpointSpec | None:
        """Convert LLM response dictionary into an EndpointSpec."""
        endpoints_data = data.get("endpoints", [])
        if not endpoints_data:
            return None

        endpoints: list[EndpointDef] = []
        for ep in endpoints_data:
            if not isinstance(ep, dict) or "method" not in ep or "path" not in ep:
                continue

            params: list[ParamSpec] = []
            for p in ep.get("parameters", []):
                if isinstance(p, dict) and "name" in p:
                    params.append(
                        ParamSpec(
                            name=p["name"],
                            location=p.get("location", "query"),
                            required=p.get("required", False),
                            type=p.get("type", "str"),
                            example=p.get("example"),
                        )
                    )

            endpoints.append(
                EndpointDef(
                    method=ep["method"].upper(),
                    path=ep["path"],
                    operation_id=ep.get("operation_id", f"{ep['method'].lower()}_endpoint"),
                    summary=ep.get("summary", ""),
                    parameters=params,
                    request_body_required=ep.get("request_body_required", False),
                    request_body_sample=ep.get("request_body_sample"),
                    extra_headers=ep.get("extra_headers", {}),
                )
            )

        if not endpoints:
            return None

        auth_data = data.get("auth", {})
        auth_info = AuthInfo(
            type=auth_data.get("type", "none"),
            header_name=auth_data.get("header_name", ""),
            scheme=auth_data.get("scheme", ""),
            required_env_vars=auth_data.get("required_env_vars", []),
        )

        return EndpointSpec(
            title=data.get("title", "ApiClient"),
            base_url=data.get("base_url", ""),
            endpoints=endpoints,
            auth=auth_info,
            source_format="llm",
        )
