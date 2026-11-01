"""Unit tests for Normalizer, Jinja2 codegen, and mandatory AST parse validation."""

from __future__ import annotations

import ast
from pathlib import Path

from smartdevtool.wrapper.inputs import CurlParser, PostmanParser, HarParser, DocParser
from smartdevtool.wrapper.normalizer import Normalizer
from smartdevtool.wrapper.codegen import WrapperGenerator


def test_codegen_from_curl():
    """Generate wrapper from curl command and verify ast.parse()."""
    cmd = (
        'curl -X POST "https://api.example.com/v1/users/{user_id}?notify=true" '
        '-H "Authorization: Bearer my_jwt" '
        '-d \'{"email": "test@example.com"}\''
    )
    spec = CurlParser(cmd).parse()
    generator = WrapperGenerator(spec, class_name="UserApiClient")
    code = generator.generate_code()

    # Hard AST parse check
    tree = ast.parse(code)
    assert tree is not None
    assert "class UserApiClient" in code
    assert "def post_users" in code


def test_codegen_from_postman(tmp_path: Path):
    """Generate wrapper from Postman collection and verify ast.parse()."""
    col = Path("examples/sample_postman_collection.json")
    spec = PostmanParser(col).parse()
    generator = WrapperGenerator(spec)
    code = generator.generate_code()

    tree = ast.parse(code)
    assert tree is not None
    assert "class DemoAPIClient" in code


def test_codegen_from_openapi():
    """Generate wrapper from OpenAPI specification and verify ast.parse()."""
    doc = Path("examples/sample_openapi.json")
    spec = DocParser(doc).parse()
    generator = WrapperGenerator(spec)
    code = generator.generate_code()

    tree = ast.parse(code)
    assert tree is not None
    assert "class DemoAPIClient" in code


def test_normalizer_merge_and_codegen():
    """Merge curl and doc specs, verify deduplication and clean AST generation."""
    spec_curl = CurlParser('curl -X GET "https://api.example.com/v1/items"').parse()
    spec_doc = DocParser(
        "Base URL: https://api.example.com\nGET /v1/items\nPOST /v1/items"
    ).parse()

    merged = Normalizer.merge([spec_curl, spec_doc])
    assert len(merged.endpoints) == 2  # GET /v1/items deduplicated, POST /v1/items kept

    generator = WrapperGenerator(merged, class_name="MergedApiClient")
    code = generator.generate_code()
    tree = ast.parse(code)
    assert tree is not None
    assert "def get_items" in code
    assert "def post_items" in code
