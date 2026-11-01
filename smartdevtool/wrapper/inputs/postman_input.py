"""Parser for Postman Collection v2.x JSON exports.

Recursively flattens nested folder trees and resolves both collection-level
and request-level authentication blocks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from smartdevtool.wrapper.auth_detector import classify_header, classify_postman_auth
from smartdevtool.wrapper.spec import EndpointDef, EndpointSpec, ParamSpec


def _make_operation_id(name: str, method: str, path: str) -> str:
    """Generate a clean operation id from request name or path."""
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_").lower()
    if clean_name and not clean_name.isdigit():
        return clean_name
    clean_path = re.sub(r"[{}\[\]:]", "", path).strip("/")
    parts = [p for p in re.split(r"[/_-]", clean_path) if p]
    return f"{method.lower()}_{'_'.join(parts) if parts else 'root'}"


class PostmanParser:
    """Parses Postman v2.x Collection JSON into an EndpointSpec."""

    def __init__(self, file_path_or_content: str | Path) -> None:
        self.raw_data = self._load_json(file_path_or_content)

    def _load_json(self, source: str | Path) -> dict[str, Any]:
        """Load JSON from filepath or raw JSON string."""
        if isinstance(source, Path) or (isinstance(source, str) and (source.endswith(".json") or Path(source).is_file())):
            try:
                with open(source, encoding="utf-8-sig") as f:
                    return json.load(f)
            except Exception:
                pass
        try:
            return json.loads(str(source))
        except Exception:
            return {}

    def parse(self) -> EndpointSpec:
        """Parse collection and return normalized EndpointSpec."""
        if not self.raw_data:
            return EndpointSpec(source_format="postman")

        info = self.raw_data.get("info", {})
        title = info.get("name", "PostmanApi")
        api_slug = re.sub(r"[^a-zA-Z0-9]", "", title) or "API"

        collection_auth = classify_postman_auth(self.raw_data.get("auth"), api_slug=api_slug)

        raw_items = self.raw_data.get("item", [])
        flat_requests = self._flatten_items(raw_items)

        endpoints: list[EndpointDef] = []
        base_urls: list[str] = []
        primary_auth = collection_auth

        for item in flat_requests:
            req = item.get("request")
            if not req:
                continue

            item_name = item.get("name", "")
            method = req.get("method", "GET").upper()
            url_obj = req.get("url")

            raw_url = ""
            query_items: list[dict[str, Any]] = []
            path_variables: list[dict[str, Any]] = []

            if isinstance(url_obj, str):
                raw_url = url_obj
            elif isinstance(url_obj, dict):
                raw_url = url_obj.get("raw", "")
                query_items = url_obj.get("query", [])
                path_variables = url_obj.get("variable", [])

            if not raw_url:
                continue

            parsed_url = urlparse(raw_url)
            if parsed_url.scheme and parsed_url.netloc:
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                if base_url not in base_urls:
                    base_urls.append(base_url)
            path = parsed_url.path or "/"

            parameters: list[ParamSpec] = []

            # Query parameters
            for q in query_items:
                q_key = q.get("key")
                if q_key:
                    parameters.append(
                        ParamSpec(
                            name=q_key,
                            location="query",
                            required=False,
                            type="str",
                            example=q.get("value"),
                        )
                    )

            # Query params from URL string if query_items was empty
            if not query_items and parsed_url.query:
                q_dict = parse_qs(parsed_url.query)
                for q_key, q_vals in q_dict.items():
                    parameters.append(
                        ParamSpec(
                            name=q_key,
                            location="query",
                            required=False,
                            type="str",
                            example=q_vals[0] if q_vals else None,
                        )
                    )

            # Path variables
            for p_var in path_variables:
                p_key = p_var.get("key")
                if p_key:
                    parameters.append(
                        ParamSpec(
                            name=p_key,
                            location="path",
                            required=True,
                            type="str",
                            example=p_var.get("value"),
                        )
                    )

            path_matches = re.findall(r"\{([a-zA-Z0-9_]+)\}|:([a-zA-Z0-9_]+)", path)
            for m1, m2 in path_matches:
                p_key = m1 or m2
                if not any(p.name == p_key for p in parameters):
                    parameters.append(
                        ParamSpec(
                            name=p_key,
                            location="path",
                            required=True,
                            type="str",
                        )
                    )

            # Headers
            headers_list = req.get("header", [])
            extra_headers: dict[str, str] = {}
            for h in headers_list:
                hk = h.get("key", "")
                hv = h.get("value", "")
                if hk:
                    if primary_auth.type == "none":
                        det = classify_header(hk, hv, api_slug=api_slug)
                        if det.type != "none":
                            primary_auth = det
                            continue
                    extra_headers[hk] = hv

            # Request auth override if collection auth wasn't present
            if primary_auth.type == "none" and req.get("auth"):
                primary_auth = classify_postman_auth(req.get("auth"), api_slug=api_slug)

            # Request body
            body_obj = req.get("body", {})
            request_body_required = False
            request_body_sample = None
            if body_obj:
                raw_body = body_obj.get("raw")
                if raw_body:
                    request_body_required = True
                    try:
                        request_body_sample = json.loads(raw_body)
                    except Exception:
                        request_body_sample = raw_body

            op_id = _make_operation_id(item_name, method, path)

            endpoints.append(
                EndpointDef(
                    method=method,
                    path=path,
                    operation_id=op_id,
                    summary=item_name or f"{method} {path}",
                    parameters=parameters,
                    request_body_required=request_body_required,
                    request_body_sample=request_body_sample,
                    extra_headers=extra_headers,
                )
            )

        chosen_base = base_urls[0] if base_urls else ""

        return EndpointSpec(
            title=f"{title.replace(' ', '')}Client",
            base_url=chosen_base,
            endpoints=endpoints,
            auth=primary_auth,
            source_format="postman",
        )

    def _flatten_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Recursively traverse folder hierarchies to return a flat list of request items."""
        result: list[dict[str, Any]] = []
        for item in items:
            if "item" in item and isinstance(item["item"], list):
                result.extend(self._flatten_items(item["item"]))
            elif "request" in item:
                result.append(item)
        return result
