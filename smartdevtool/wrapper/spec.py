"""The normalization contract for API wrapper generation.

Every input parser (curl, Postman, HAR, OpenAPI/docs) targets this exact dataclass
hierarchy. Downstream components (normalizer, codegen, validation agent) interact
strictly with EndpointSpec and never touch source-format specifics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AuthType = Literal["api_key", "jwt", "oauth2", "basic_auth", "none"]
ParamLocation = Literal["query", "path", "header", "body"]


@dataclass
class ParamSpec:
    """Specification of an endpoint parameter."""

    name: str
    location: ParamLocation = "query"
    required: bool = False
    type: str = "str"
    example: Any | None = None


@dataclass
class AuthInfo:
    """Authentication classification and required environment variable metadata."""

    type: AuthType = "none"
    header_name: str = ""
    scheme: str = ""
    required_env_vars: list[str] = field(default_factory=list)


@dataclass
class EndpointDef:
    """Definition of a single API endpoint."""

    method: str
    path: str
    operation_id: str
    summary: str = ""
    parameters: list[ParamSpec] = field(default_factory=list)
    request_body_required: bool = False
    request_body_sample: Any | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class EndpointSpec:
    """Normalized API specification produced by any input parser."""

    title: str = "ApiWrapper"
    base_url: str = ""
    endpoints: list[EndpointDef] = field(default_factory=list)
    auth: AuthInfo = field(default_factory=AuthInfo)
    source_format: str = ""
