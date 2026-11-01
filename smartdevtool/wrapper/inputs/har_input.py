"""Parser for browser HTTP Archive (.har) capture files.

Filters signal from noise by excluding static assets and tracker domains,
keeping JSON/API-like traffic, grouping by host, and extracting working endpoints.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from smartdevtool.wrapper.auth_detector import classify_header
from smartdevtool.wrapper.spec import AuthInfo, EndpointDef, EndpointSpec, ParamSpec

STATIC_EXTENSIONS = {
    ".js",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".map",
    ".mp4",
    ".webm",
    ".webp",
    ".html",
    ".htm",
}

TRACKER_DOMAINS = {
    "google-analytics.com",
    "doubleclick.net",
    "facebook.com",
    "facebook.net",
    "analytics.google.com",
    "googletagmanager.com",
    "hotjar.com",
    "sentry.io",
    "mixpanel.com",
    "segment.io",
    "clarity.ms",
    "datadoghq.com",
}


def _make_operation_id(method: str, path: str) -> str:
    """Generate pythonic operation ID."""
    clean_path = re.sub(r"[{}\[\]:]", "", path).strip("/")
    parts = [p for p in re.split(r"[/_-]", clean_path) if p and not p.startswith("v1") and not p.startswith("v2")]
    if not parts:
        parts = ["root"]
    return f"{method.lower()}_{'_'.join(parts)}"


class HarParser:
    """Parses HAR files, filtering noise and extracting API endpoints from the primary host."""

    def __init__(self, file_path_or_content: str | Path) -> None:
        self.raw_data = self._load_har(file_path_or_content)

    def _load_har(self, source: str | Path) -> dict[str, Any]:
        """Load HAR from file or string."""
        if isinstance(source, Path) or (isinstance(source, str) and (source.endswith(".har") or Path(source).is_file())):
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
        """Filter entries and build EndpointSpec."""
        if not self.raw_data:
            return EndpointSpec(source_format="har")

        entries = self.raw_data.get("log", {}).get("entries", [])
        if not entries:
            return EndpointSpec(source_format="har")

        # Step 1: Filter signal from noise
        candidates: list[dict[str, Any]] = []
        host_counts: Counter[str] = Counter()

        for entry in entries:
            req = entry.get("request", {})
            resp = entry.get("response", {})
            url_str = req.get("url", "")
            if not url_str:
                continue

            parsed = urlparse(url_str)
            netloc = parsed.netloc.lower()
            path = parsed.path.lower()

            # Exclude known tracker domains
            if any(tracker in netloc for tracker in TRACKER_DOMAINS):
                continue

            # Exclude static asset extensions
            ext = Path(path).suffix
            if ext in STATIC_EXTENSIONS:
                continue

            # Check if JSON-like or API-like
            req_headers = {h.get("name", "").lower(): h.get("value", "") for h in req.get("headers", [])}
            resp_mime = resp.get("content", {}).get("mimeType", "").lower()
            accept_hdr = req_headers.get("accept", "").lower()

            is_json = "json" in resp_mime or "json" in accept_hdr
            is_api_path = any(x in path for x in ["/api", "/v1", "/v2", "/v3", "/graphql", "/rest"])
            is_mutating = req.get("method", "").upper() in ["POST", "PUT", "PATCH", "DELETE"]
            is_api_domain = "api." in netloc

            if is_json or is_api_path or is_mutating or is_api_domain:
                candidates.append(entry)
                host_counts[netloc] += 1

        if not candidates or not host_counts:
            return EndpointSpec(source_format="har")

        # Step 2: Pick the most common domain as primary API host
        primary_host = host_counts.most_common(1)[0][0]
        api_slug = primary_host.split(".")[0].replace("-", "") or "API"
        base_url = ""
        endpoints: list[EndpointDef] = []
        seen_keys: set[tuple[str, str]] = set()
        primary_auth = AuthInfo(type="none")

        for entry in candidates:
            req = entry.get("request", {})
            url_str = req.get("url", "")
            parsed = urlparse(url_str)

            if parsed.netloc.lower() != primary_host:
                continue

            if not base_url:
                base_url = f"{parsed.scheme}://{parsed.netloc}"

            method = req.get("method", "GET").upper()
            path = parsed.path or "/"

            key = (method, path)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Parameters
            parameters: list[ParamSpec] = []
            if req.get("queryString"):
                for q in req["queryString"]:
                    parameters.append(
                        ParamSpec(
                            name=q.get("name", ""),
                            location="query",
                            required=False,
                            type="str",
                            example=q.get("value"),
                        )
                    )
            elif parsed.query:
                q_dict = parse_qs(parsed.query)
                for qk, qvs in q_dict.items():
                    parameters.append(
                        ParamSpec(
                            name=qk,
                            location="query",
                            required=False,
                            type="str",
                            example=qvs[0] if qvs else None,
                        )
                    )

            # Headers & Auth
            extra_headers: dict[str, str] = {}
            for h in req.get("headers", []):
                hn = h.get("name", "")
                hv = h.get("value", "")
                if hn:
                    if primary_auth.type == "none":
                        det = classify_header(hn, hv, api_slug=api_slug)
                        if det.type != "none":
                            primary_auth = det
                            continue
                    if hn.lower() not in ("host", "content-length", "cookie"):
                        extra_headers[hn] = hv

            # Body
            request_body_required = False
            request_body_sample = None
            post_data = req.get("postData")
            if post_data and post_data.get("text"):
                request_body_required = True
                try:
                    request_body_sample = json.loads(post_data["text"])
                except Exception:
                    request_body_sample = post_data["text"]

            op_id = _make_operation_id(method, path)

            endpoints.append(
                EndpointDef(
                    method=method,
                    path=path,
                    operation_id=op_id,
                    summary=f"{method} {path}",
                    parameters=parameters,
                    request_body_required=request_body_required,
                    request_body_sample=request_body_sample,
                    extra_headers=extra_headers,
                )
            )

        title = f"{api_slug.capitalize()}Client"

        return EndpointSpec(
            title=title,
            base_url=base_url,
            endpoints=endpoints,
            auth=primary_auth,
            source_format="har",
        )
