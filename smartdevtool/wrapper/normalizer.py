"""Endpoint specification normalizer and merger.

Combines multiple EndpointSpecs when a developer passes multiple inputs
in a single run (e.g. both a curl command and an OpenAPI doc).
Deduplicates by (method, path); first spec's auth and base_url win on conflict.
"""

from __future__ import annotations

from smartdevtool.wrapper.spec import AuthInfo, EndpointDef, EndpointSpec


class Normalizer:
    """Normalizes and merges multiple EndpointSpec inputs into a cohesive specification."""

    @staticmethod
    def merge(specs: list[EndpointSpec]) -> EndpointSpec:
        """Merge multiple EndpointSpec instances into a single normalized spec."""
        if not specs:
            return EndpointSpec()

        first = specs[0]
        merged_title = first.title
        merged_base_url = ""
        merged_auth = AuthInfo(type="none")
        source_formats: list[str] = []

        # Determine primary base_url and auth
        for spec in specs:
            if spec.source_format and spec.source_format not in source_formats:
                source_formats.append(spec.source_format)

            if not merged_base_url and spec.base_url:
                merged_base_url = spec.base_url

            if merged_auth.type == "none" and spec.auth.type != "none":
                merged_auth = spec.auth

        # If title is default and a later spec has a custom title, adopt it
        for spec in specs:
            if spec.title and spec.title not in ("ApiWrapper", "ApiClient"):
                merged_title = spec.title
                break

        # Merge and deduplicate endpoints by (method, path)
        seen_endpoints: set[tuple[str, str]] = set()
        merged_endpoints: list[EndpointDef] = []

        for spec in specs:
            for ep in spec.endpoints:
                key = (ep.method.upper(), ep.path)
                if key not in seen_endpoints:
                    seen_endpoints.add(key)
                    merged_endpoints.append(ep)

        return EndpointSpec(
            title=merged_title,
            base_url=merged_base_url,
            endpoints=merged_endpoints,
            auth=merged_auth,
            source_format="+".join(source_formats) if source_formats else "merged",
        )
