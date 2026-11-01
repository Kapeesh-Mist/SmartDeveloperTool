"""Parser for OpenAPI 3.x / Swagger 2.0 specs and unstructured prose API docs.

Tries structured JSON/YAML spec parsing first.
Falls back to deterministic regex / keyword scanning for prose documentation pages.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from smartdevtool.wrapper.auth_detector import classify_openapi_scheme
from smartdevtool.wrapper.spec import AuthInfo, EndpointDef, EndpointSpec, ParamSpec


def _make_operation_id(method: str, path: str) -> str:
    """Generate clean method name."""
    clean_path = re.sub(r"[{}\[\]:]", "", path).strip("/")
    parts = [p for p in re.split(r"[/_-]", clean_path) if p and not p.startswith("v1") and not p.startswith("v2")]
    if not parts:
        parts = ["root"]
    return f"{method.lower()}_{'_'.join(parts)}"


class DocParser:
    """Parses OpenAPI specifications and prose documentation into an EndpointSpec."""

    def __init__(self, source: str | Path) -> None:
        self.raw_text = self._load_source(source)

    def _load_source(self, source: str | Path) -> str:
        """Load text from file path, remote URL, or raw string."""
        s = str(source).strip()
        # Check if local file
        if isinstance(source, Path) or Path(s).is_file():
            try:
                with open(source, encoding="utf-8-sig") as f:
                    return f.read()
            except Exception:
                pass

        # Check if URL
        if s.startswith(("http://", "https://")):
            try:
                resp = httpx.get(s, timeout=10.0, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.text
            except Exception:
                pass

        return s

    def parse(self) -> EndpointSpec:
        """Parse structured OpenAPI or fallback to prose keyword scanner."""
        # Try structured parse
        spec_dict = self._try_parse_spec(self.raw_text)
        if spec_dict and ("openapi" in spec_dict or "swagger" in spec_dict):
            structured = self._parse_structured_openapi(spec_dict)
            if structured.endpoints:
                return structured

        # Fallback to prose regex scanner
        return self._parse_prose(self.raw_text)

    def _try_parse_spec(self, text: str) -> dict[str, Any] | None:
        """Try parsing JSON, then YAML."""
        if not text.strip():
            return None
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    def _parse_structured_openapi(self, doc: dict[str, Any]) -> EndpointSpec:
        """Parse formal OpenAPI 3.x or Swagger 2.0 dictionary."""
        info = doc.get("info", {})
        title = info.get("title", "OpenApi").replace(" ", "")
        api_slug = re.sub(r"[^a-zA-Z0-9]", "", title) or "API"

        # Determine base URL
        base_url = ""
        servers = doc.get("servers", [])
        if servers and isinstance(servers, list):
            base_url = servers[0].get("url", "")
        elif "host" in doc:
            schemes = doc.get("schemes", ["https"])
            scheme = schemes[0] if schemes else "https"
            base_path = doc.get("basePath", "")
            base_url = f"{scheme}://{doc['host']}{base_path}".rstrip("/")

        # Auth classification
        auth_info = AuthInfo(type="none")
        # OpenAPI 3
        security_schemes = doc.get("components", {}).get("securitySchemes", {})
        # Swagger 2
        if not security_schemes:
            security_schemes = doc.get("securityDefinitions", {})

        for s_name, s_def in security_schemes.items():
            if isinstance(s_def, dict):
                s_type = s_def.get("type", "")
                det = classify_openapi_scheme(s_type, s_def, api_slug=api_slug)
                if det.type != "none":
                    auth_info = det
                    break

        endpoints: list[EndpointDef] = []
        paths = doc.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                if method not in path_item:
                    continue
                op = path_item[method]
                if not isinstance(op, dict):
                    continue

                operation_id = op.get("operationId") or _make_operation_id(method, path)
                summary = op.get("summary") or op.get("description") or f"{method.upper()} {path}"

                # Parameters
                parameters: list[ParamSpec] = []
                params_list = op.get("parameters", [])
                if isinstance(path_item.get("parameters"), list):
                    params_list = path_item["parameters"] + params_list

                for p in params_list:
                    if isinstance(p, dict) and "name" in p:
                        parameters.append(
                            ParamSpec(
                                name=p["name"],
                                location=p.get("in", "query"),
                                required=p.get("required", False),
                                type=p.get("schema", {}).get("type", "str") if isinstance(p.get("schema"), dict) else "str",
                                example=p.get("example"),
                            )
                        )

                # Request body (OpenAPI 3)
                request_body_required = False
                request_body_sample = None
                req_body = op.get("requestBody", {})
                if isinstance(req_body, dict):
                    request_body_required = req_body.get("required", False)
                    content = req_body.get("content", {})
                    for mime in ["application/json", "*/*"]:
                        if mime in content:
                            schema = content[mime].get("schema", {})
                            request_body_sample = schema.get("example")

                # Body param (Swagger 2)
                for p in params_list:
                    if isinstance(p, dict) and p.get("in") == "body":
                        request_body_required = p.get("required", False)
                        request_body_sample = p.get("schema", {}).get("example")

                endpoints.append(
                    EndpointDef(
                        method=method.upper(),
                        path=path,
                        operation_id=operation_id,
                        summary=summary,
                        parameters=parameters,
                        request_body_required=request_body_required,
                        request_body_sample=request_body_sample,
                        extra_headers={},
                    )
                )

        return EndpointSpec(
            title=f"{title}Client",
            base_url=base_url,
            endpoints=endpoints,
            auth=auth_info,
            source_format="doc",
        )

    def _parse_prose(self, text: str) -> EndpointSpec:
        """Deterministic regex scanner for unstructured prose documentation."""
        text_lower = text.lower()
        endpoints: list[EndpointDef] = []

        # Find base URL if mentioned
        base_match = re.search(r"https?://[a-zA-Z0-9\.\-]+(?:/[a-zA-Z0-9_\-]+)*", text)
        base_url = ""
        if base_match:
            parsed = urlparse(base_match.group(0))
            base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Regex for HTTP methods followed by paths
        pattern = r"\b(GET|POST|PUT|DELETE|PATCH)\s+([/][a-zA-Z0-9_\-/{}:]+)"
        matches = re.findall(pattern, text, re.IGNORECASE)

        seen: set[tuple[str, str]] = set()
        for m_str, p_str in matches:
            method = m_str.upper()
            path = p_str.strip()
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)

            parameters: list[ParamSpec] = []
            path_vars = re.findall(r"\{([a-zA-Z0-9_]+)\}|:([a-zA-Z0-9_]+)", path)
            for v1, v2 in path_vars:
                parameters.append(
                    ParamSpec(
                        name=v1 or v2,
                        location="path",
                        required=True,
                        type="str",
                    )
                )

            op_id = _make_operation_id(method, path)
            endpoints.append(
                EndpointDef(
                    method=method,
                    path=path,
                    operation_id=op_id,
                    summary=f"{method} {path}",
                    parameters=parameters,
                    request_body_required=(method in ["POST", "PUT", "PATCH"]),
                    request_body_sample=None,
                    extra_headers={},
                )
            )

        # Scan for auth keywords
        auth_info = AuthInfo(type="none")
        if "bearer" in text_lower or "jwt" in text_lower:
            auth_info = AuthInfo(
                type="jwt",
                header_name="Authorization",
                scheme="Bearer",
                required_env_vars=["API_TOKEN"],
            )
        elif "api key" in text_lower or "x-api-key" in text_lower or "apikey" in text_lower:
            auth_info = AuthInfo(
                type="api_key",
                header_name="X-Api-Key",
                scheme="",
                required_env_vars=["API_KEY"],
            )
        elif "basic auth" in text_lower:
            auth_info = AuthInfo(
                type="basic_auth",
                header_name="Authorization",
                scheme="Basic",
                required_env_vars=["API_USERNAME", "API_PASSWORD"],
            )

        return EndpointSpec(
            title="ApiClient",
            base_url=base_url,
            endpoints=endpoints,
            auth=auth_info,
            source_format="doc",
        )
