"""Hand-rolled curl parser using Python's stdlib `shlex`.

Does not rely on unmaintained third-party packages.
Captures real, working HTTP requests directly from developer curl commands.
"""

from __future__ import annotations

import json
import re
import shlex
from urllib.parse import urlparse, parse_qs

from smartdevtool.wrapper.auth_detector import classify_header
from smartdevtool.wrapper.spec import AuthInfo, EndpointDef, EndpointSpec, ParamSpec


def _make_operation_id(method: str, path: str) -> str:
    """Generate a clean, pythonic method name from HTTP method and URL path."""
    clean_path = re.sub(r"[{}\[\]:]", "", path).strip("/")
    parts = [p for p in re.split(r"[/_-]", clean_path) if p and not p.startswith("v1") and not p.startswith("v2")]
    if not parts:
        parts = ["root"]
    return f"{method.lower()}_{'_'.join(parts)}"


class CurlParser:
    """Parses curl command strings into normalized EndpointSpec objects."""

    def __init__(self, curl_command: str) -> None:
        self.raw_command = curl_command.strip()

    def parse(self) -> EndpointSpec:
        """Parse the curl command and return an EndpointSpec."""
        tokens = shlex.split(self.raw_command)
        if not tokens:
            return EndpointSpec(source_format="curl")

        # Skip leading 'curl' if present
        if tokens[0].lower() == "curl":
            tokens = tokens[1:]

        method: str | None = None
        url_str: str | None = None
        headers: dict[str, str] = {}
        data_payload: str | None = None
        basic_user: str | None = None

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token in ("-X", "--request") and i + 1 < len(tokens):
                method = tokens[i + 1].upper()
                i += 2
            elif token in ("-H", "--header") and i + 1 < len(tokens):
                header_line = tokens[i + 1]
                if ":" in header_line:
                    k, v = header_line.split(":", 1)
                    headers[k.strip()] = v.strip()
                i += 2
            elif token in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii") and i + 1 < len(tokens):
                data_payload = tokens[i + 1]
                i += 2
            elif token in ("-u", "--user") and i + 1 < len(tokens):
                basic_user = tokens[i + 1]
                i += 2
            elif token.startswith("http://") or token.startswith("https://"):
                url_str = token
                i += 1
            elif not token.startswith("-") and url_str is None:
                # Might be URL without http prefix or flag
                url_str = token
                i += 1
            else:
                # Ignore unknown/non-critical flags (e.g. -s, -v, -k)
                i += 1

        if not url_str:
            return EndpointSpec(source_format="curl")

        if not url_str.startswith(("http://", "https://")):
            url_str = f"https://{url_str}"

        parsed_url = urlparse(url_str)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        path = parsed_url.path or "/"

        # If data is present and no explicit method was given, default to POST
        if method is None:
            method = "POST" if data_payload is not None else "GET"

        # Parameters
        parameters: list[ParamSpec] = []

        # Query params
        if parsed_url.query:
            query_dict = parse_qs(parsed_url.query)
            for q_name, q_vals in query_dict.items():
                example = q_vals[0] if q_vals else None
                parameters.append(
                    ParamSpec(
                        name=q_name,
                        location="query",
                        required=False,
                        type="str",
                        example=example,
                    )
                )

        # Path params
        path_vars = re.findall(r"\{([a-zA-Z0-9_]+)\}|:([a-zA-Z0-9_]+)", path)
        for var1, var2 in path_vars:
            p_name = var1 or var2
            parameters.append(
                ParamSpec(
                    name=p_name,
                    location="path",
                    required=True,
                    type="str",
                )
            )

        # Body parsing
        request_body_required = False
        request_body_sample = None
        if data_payload is not None:
            request_body_required = True
            try:
                request_body_sample = json.loads(data_payload)
            except Exception:
                request_body_sample = data_payload

        # Auth classification
        auth_info = AuthInfo(type="none")
        api_slug = parsed_url.netloc.split(".")[0] or "API"
        extra_headers: dict[str, str] = {}

        if basic_user:
            auth_info = AuthInfo(
                type="basic_auth",
                header_name="Authorization",
                scheme="Basic",
                required_env_vars=[f"{api_slug.upper()}_USERNAME", f"{api_slug.upper()}_PASSWORD"],
            )

        for h_name, h_val in headers.items():
            if auth_info.type == "none":
                detected = classify_header(h_name, h_val, api_slug=api_slug)
                if detected.type != "none":
                    auth_info = detected
                    continue
            extra_headers[h_name] = h_val

        operation_id = _make_operation_id(method, path)

        endpoint_def = EndpointDef(
            method=method,
            path=path,
            operation_id=operation_id,
            summary=f"{method} {path}",
            parameters=parameters,
            request_body_required=request_body_required,
            request_body_sample=request_body_sample,
            extra_headers=extra_headers,
        )

        title = f"{api_slug.capitalize()}Client"

        return EndpointSpec(
            title=title,
            base_url=base_url,
            endpoints=[endpoint_def],
            auth=auth_info,
            source_format="curl",
        )
