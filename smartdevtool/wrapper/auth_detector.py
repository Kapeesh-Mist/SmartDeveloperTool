"""Shared authentication classification module for all input parsers.

Classifies headers and auth blocks into AuthInfo contracts, generating
idiomatic environment variable names for configuration.
"""

from __future__ import annotations

import re
from typing import Any

from smartdevtool.wrapper.spec import AuthInfo


def _slugify_env(slug: str, suffix: str) -> str:
    """Format an uppercase safe environment variable name."""
    clean_slug = re.sub(r"[^a-zA-Z0-9_]", "_", slug).strip("_").upper()
    if not clean_slug:
        clean_slug = "API"
    return f"{clean_slug}_{suffix.upper()}"


def classify_header(name: str, value: str = "", api_slug: str = "API") -> AuthInfo:
    """Classify real HTTP request headers captured from curl or HAR.

    Highest confidence classification because it reflects a request that actually worked.
    """
    lower_name = name.lower().strip()
    val_clean = value.strip()

    if lower_name == "authorization":
        if val_clean.lower().startswith("bearer "):
            return AuthInfo(
                type="jwt",
                header_name="Authorization",
                scheme="Bearer",
                required_env_vars=[_slugify_env(api_slug, "TOKEN")],
            )
        elif val_clean.lower().startswith("basic "):
            return AuthInfo(
                type="basic_auth",
                header_name="Authorization",
                scheme="Basic",
                required_env_vars=[
                    _slugify_env(api_slug, "USERNAME"),
                    _slugify_env(api_slug, "PASSWORD"),
                ],
            )
        elif val_clean.lower().startswith("token "):
            return AuthInfo(
                type="api_key",
                header_name="Authorization",
                scheme="Token",
                required_env_vars=[_slugify_env(api_slug, "API_KEY")],
            )
        else:
            return AuthInfo(
                type="api_key",
                header_name="Authorization",
                scheme="Bearer",
                required_env_vars=[_slugify_env(api_slug, "API_KEY")],
            )

    # Dedicated API key headers
    api_key_patterns = ["api-key", "apikey", "x-api-key", "x-auth-token", "token"]
    if any(pat in lower_name for pat in api_key_patterns):
        return AuthInfo(
            type="api_key",
            header_name=name,
            scheme="",
            required_env_vars=[_slugify_env(api_slug, "API_KEY")],
        )

    return AuthInfo(type="none")


def classify_postman_auth(auth_dict: dict[str, Any] | None, api_slug: str = "API") -> AuthInfo:
    """Classify Postman collection or request auth block."""
    if not auth_dict or not isinstance(auth_dict, dict):
        return AuthInfo(type="none")

    auth_type = auth_dict.get("type", "").lower()

    if auth_type == "bearer":
        return AuthInfo(
            type="jwt",
            header_name="Authorization",
            scheme="Bearer",
            required_env_vars=[_slugify_env(api_slug, "TOKEN")],
        )
    elif auth_type == "apikey":
        apikey_params = auth_dict.get("apikey", [])
        header_name = "X-Api-Key"
        if isinstance(apikey_params, list):
            for item in apikey_params:
                if item.get("key") == "key":
                    header_name = item.get("value", "X-Api-Key")
        return AuthInfo(
            type="api_key",
            header_name=header_name,
            scheme="",
            required_env_vars=[_slugify_env(api_slug, "API_KEY")],
        )
    elif auth_type == "basic":
        return AuthInfo(
            type="basic_auth",
            header_name="Authorization",
            scheme="Basic",
            required_env_vars=[
                _slugify_env(api_slug, "USERNAME"),
                _slugify_env(api_slug, "PASSWORD"),
            ],
        )
    elif auth_type == "oauth2":
        return AuthInfo(
            type="oauth2",
            header_name="Authorization",
            scheme="Bearer",
            required_env_vars=[_slugify_env(api_slug, "ACCESS_TOKEN")],
        )

    return AuthInfo(type="none")


def classify_openapi_scheme(
    scheme_type: str, scheme_dict: dict[str, Any], api_slug: str = "API"
) -> AuthInfo:
    """Classify OpenAPI 3.x / Swagger 2.0 security schemes."""
    st = scheme_type.lower()

    if st == "apikey":
        header_name = scheme_dict.get("name", "X-Api-Key")
        return AuthInfo(
            type="api_key",
            header_name=header_name,
            scheme="",
            required_env_vars=[_slugify_env(api_slug, "API_KEY")],
        )
    elif st == "http":
        scheme = scheme_dict.get("scheme", "").lower()
        if scheme == "bearer":
            return AuthInfo(
                type="jwt",
                header_name="Authorization",
                scheme="Bearer",
                required_env_vars=[_slugify_env(api_slug, "TOKEN")],
            )
        elif scheme == "basic":
            return AuthInfo(
                type="basic_auth",
                header_name="Authorization",
                scheme="Basic",
                required_env_vars=[
                    _slugify_env(api_slug, "USERNAME"),
                    _slugify_env(api_slug, "PASSWORD"),
                ],
            )
    elif st == "oauth2":
        return AuthInfo(
            type="oauth2",
            header_name="Authorization",
            scheme="Bearer",
            required_env_vars=[_slugify_env(api_slug, "ACCESS_TOKEN")],
        )

    return AuthInfo(type="none")
