"""Unit tests for Feature 1's spec, auth_detector, and all 4 input parsers."""

from __future__ import annotations

import json
from pathlib import Path

from smartdevtool.wrapper.spec import EndpointSpec, ParamSpec, EndpointDef, AuthInfo
from smartdevtool.wrapper.auth_detector import classify_header, classify_postman_auth, classify_openapi_scheme
from smartdevtool.wrapper.inputs import CurlParser, PostmanParser, HarParser, DocParser


def test_auth_detector_header():
    """Verify header classification handles Bearer, Basic, and custom API key headers."""
    jwt_auth = classify_header("Authorization", "Bearer eyJhbGciOi...", api_slug="github")
    assert jwt_auth.type == "jwt"
    assert jwt_auth.scheme == "Bearer"
    assert "GITHUB_TOKEN" in jwt_auth.required_env_vars

    basic_auth = classify_header("Authorization", "Basic dXNlcjpwYXNz", api_slug="service")
    assert basic_auth.type == "basic_auth"
    assert basic_auth.scheme == "Basic"
    assert "SERVICE_USERNAME" in basic_auth.required_env_vars

    key_auth = classify_header("X-API-KEY", "secret-val", api_slug="stripe")
    assert key_auth.type == "api_key"
    assert key_auth.header_name == "X-API-KEY"
    assert "STRIPE_API_KEY" in key_auth.required_env_vars


def test_curl_parser_shlex():
    """Verify curl parser correctly extracts method, path, params, body, and auth."""
    cmd = (
        'curl -X POST "https://api.petstore.com/v1/pets/{pet_id}?status=active" '
        '-H "Authorization: Bearer secret_token" '
        '-H "Content-Type: application/json" '
        '-d \'{"name": "Fido", "tag": "dog"}\''
    )
    parser = CurlParser(cmd)
    spec = parser.parse()

    assert spec.source_format == "curl"
    assert spec.base_url == "https://api.petstore.com"
    assert spec.auth.type == "jwt"
    assert len(spec.endpoints) == 1

    ep = spec.endpoints[0]
    assert ep.method == "POST"
    assert ep.path == "/v1/pets/{pet_id}"
    assert ep.request_body_required is True
    assert ep.request_body_sample == {"name": "Fido", "tag": "dog"}

    param_names = {p.name: p.location for p in ep.parameters}
    assert param_names.get("status") == "query"
    assert param_names.get("pet_id") == "path"


def test_postman_parser_nested_hierarchy(tmp_path: Path):
    """Verify Postman parser flattens folders and captures collection auth."""
    collection = {
        "info": {"name": "Inventory API"},
        "auth": {"type": "bearer"},
        "item": [
            {
                "name": "Warehouse Folder",
                "item": [
                    {
                        "name": "List Items",
                        "request": {
                            "method": "GET",
                            "url": {
                                "raw": "https://inventory.example.com/items?limit=25",
                                "query": [{"key": "limit", "value": "25"}],
                            },
                        },
                    }
                ],
            }
        ],
    }
    col_file = tmp_path / "collection.json"
    col_file.write_text(json.dumps(collection), encoding="utf-8")

    parser = PostmanParser(col_file)
    spec = parser.parse()

    assert spec.title == "InventoryAPIClient"
    assert spec.base_url == "https://inventory.example.com"
    assert spec.auth.type == "jwt"
    assert len(spec.endpoints) == 1
    assert spec.endpoints[0].method == "GET"
    assert spec.endpoints[0].path == "/items"
    assert spec.endpoints[0].parameters[0].name == "limit"


def test_har_parser_signal_noise_filtering(tmp_path: Path):
    """Verify HAR parser removes static assets, trackers, and isolates primary host."""
    har_content = {
        "log": {
            "entries": [
                # Tracker: must be dropped
                {
                    "request": {"method": "GET", "url": "https://www.google-analytics.com/collect?v=1"},
                    "response": {"content": {"mimeType": "image/gif"}},
                },
                # Static JS: must be dropped
                {
                    "request": {"method": "GET", "url": "https://app.example.com/static/bundle.js"},
                    "response": {"content": {"mimeType": "application/javascript"}},
                },
                # Real API on primary domain
                {
                    "request": {
                        "method": "GET",
                        "url": "https://api.example.com/v1/orders",
                        "headers": [{"name": "Accept", "value": "application/json"}],
                    },
                    "response": {"content": {"mimeType": "application/json"}},
                },
                # Second API endpoint on primary domain
                {
                    "request": {
                        "method": "POST",
                        "url": "https://api.example.com/v1/orders",
                        "headers": [{"name": "X-API-KEY", "value": "abc123key"}],
                        "postData": {"text": '{"item": "book"}'},
                    },
                    "response": {"content": {"mimeType": "application/json"}},
                },
            ]
        }
    }
    har_file = tmp_path / "capture.har"
    har_file.write_text(json.dumps(har_content), encoding="utf-8")

    parser = HarParser(har_file)
    spec = parser.parse()

    assert spec.base_url == "https://api.example.com"
    assert len(spec.endpoints) == 2
    methods = {e.method for e in spec.endpoints}
    assert methods == {"GET", "POST"}
    assert spec.auth.type == "api_key"


def test_doc_parser_prose_fallback():
    """Verify doc parser falls back to regex scanner when given prose markdown."""
    prose_doc = """
# Payment Gateway Integration Guide

Welcome to our Payments API.
Base URL: https://payments.fintech.io

Authentication:
All requests must include an API Key header `X-Api-Key: <your_key>`.

Available Endpoints:
GET /v1/charges - List all previous transactions
POST /v1/charges - Create a new customer charge
DELETE /v1/charges/{charge_id} - Cancel an authorization
"""
    parser = DocParser(prose_doc)
    spec = parser.parse()

    assert spec.base_url == "https://payments.fintech.io"
    assert spec.auth.type == "api_key"
    assert len(spec.endpoints) == 3
    paths = {e.path for e in spec.endpoints}
    assert "/v1/charges" in paths
    assert "/v1/charges/{charge_id}" in paths
