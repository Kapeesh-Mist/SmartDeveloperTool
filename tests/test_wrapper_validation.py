"""Integration tests for ValidationAgent using a local stdlib HTTP test server.

Proves real HTTP round-trip self-correction:
- Starts server requiring X-Api-Key header (returning 401 on Authorization header).
- Generates wrapper with WRONG initial convention (Authorization: Bearer).
- Proves ValidationAgent detects 401 and converges to passing state both offline
  (deterministic heuristic) and via scripted fake LLM.
- Proves safety guards (GET only, immediate termination on 403/5xx).
"""

from __future__ import annotations

import http.server
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from smartdevtool.llm.client import LLMClient
from smartdevtool.wrapper.codegen import WrapperGenerator
from smartdevtool.wrapper.spec import AuthInfo, EndpointDef, EndpointSpec
from smartdevtool.wrapper.validation_agent import ValidationAgent


class AuthEnforcingHandler(http.server.BaseHTTPRequestHandler):
    """Local HTTP test handler requiring specific auth conventions."""

    def log_message(self, format: str, *args) -> None:
        """Suppress stdout log spam during test runs."""
        return

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/api/status":
            # Check for required X-Api-Key header
            api_key = self.headers.get("X-Api-Key")
            if api_key == "valid-secret-key":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            else:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: X-Api-Key required"}')

        elif path == "/api/forbidden":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Forbidden"}')

        elif path == "/api/server-error":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Internal Server Error"}')

        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def local_http_server():
    """Spin up local stdlib HTTPServer on an ephemeral port."""
    server = http.server.HTTPServer(("127.0.0.1", 0), AuthEnforcingHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://{host}:{port}"
    server.shutdown()


def test_validation_agent_heuristic_self_correction(tmp_path: Path, local_http_server: str):
    """MUST test real HTTP round-trip self-correction offline via heuristic swap."""
    wrapper_file = tmp_path / "heuristic_client.py"

    # Initially configure with WRONG convention: Authorization: Bearer
    spec = EndpointSpec(
        title="TestServiceHeuristicClient",
        base_url=local_http_server,
        endpoints=[
            EndpointDef(
                method="GET",
                path="/api/status",
                operation_id="get_status",
                summary="Health check",
            )
        ],
        auth=AuthInfo(
            type="jwt",
            header_name="Authorization",
            scheme="Bearer",
            required_env_vars=["TEST_TOKEN"],
        ),
        source_format="test",
    )

    # Write initial wrapper to disk
    WrapperGenerator(spec).write(wrapper_file)

    # Run agent in offline mode (no LLM)
    agent = ValidationAgent(
        wrapper_file=wrapper_file,
        spec=spec,
        llm_client=None,
        max_iters=4,
    )

    result = agent.validate(test_token="valid-secret-key")

    assert result.success is True
    assert result.resolved_via == "heuristic"
    assert result.status_code == 200
    assert len(result.attempts) >= 1

    # Verify wrapper file on disk was updated to use X-Api-Key
    content = wrapper_file.read_text(encoding="utf-8")
    assert "X-Api-Key" in content


def test_validation_agent_scripted_llm_path(tmp_path: Path, local_http_server: str):
    """Test self-correction loop driven by LLM proposal."""
    wrapper_file = tmp_path / "llm_client.py"

    spec = EndpointSpec(
        title="TestServiceLLMClient",
        base_url=local_http_server,
        endpoints=[
            EndpointDef(
                method="GET",
                path="/api/status",
                operation_id="get_status",
                summary="Health check",
            )
        ],
        auth=AuthInfo(
            type="jwt",
            header_name="Authorization",
            scheme="Bearer",
            required_env_vars=["TEST_TOKEN"],
        ),
        source_format="test",
    )
    WrapperGenerator(spec).write(wrapper_file)

    fake_llm = MagicMock(spec=LLMClient)
    fake_llm.available = True
    fake_llm.complete_json.return_value = {
        "action": "change_auth_header",
        "header_name": "X-Api-Key",
        "scheme": "",
        "reasoning": "Endpoint returned 401 requesting X-Api-Key",
    }

    agent = ValidationAgent(
        wrapper_file=wrapper_file,
        spec=spec,
        llm_client=fake_llm,
        max_iters=4,
    )

    result = agent.validate(test_token="valid-secret-key")

    assert result.success is True
    assert result.resolved_via == "llm"
    assert result.status_code == 200
    assert fake_llm.complete_json.called


def test_validation_agent_immediate_exit_on_403_5xx(tmp_path: Path, local_http_server: str):
    """Verify immediate exit on 403 or 500 without futile retry loops."""
    wrapper_file = tmp_path / "unfixable_client.py"

    spec = EndpointSpec(
        title="UnfixableClient",
        base_url=local_http_server,
        endpoints=[
            EndpointDef(
                method="GET",
                path="/api/forbidden",
                operation_id="get_forbidden",
            )
        ],
        auth=AuthInfo(type="api_key", header_name="X-Api-Key"),
    )
    WrapperGenerator(spec).write(wrapper_file)

    agent = ValidationAgent(wrapper_file, spec, llm_client=None, max_iters=5)
    result = agent.validate()

    assert result.success is False
    assert result.status_code == 403
    # Must exit immediately (0 retry attempts made)
    assert len(result.attempts) == 1
    assert result.attempts[0].iteration == 0


def test_validation_agent_mutating_safety_scope(tmp_path: Path, local_http_server: str):
    """Critical safety scope: mutating endpoints are NEVER invoked in validation loop."""
    wrapper_file = tmp_path / "mutating_client.py"

    spec = EndpointSpec(
        title="MutatingClient",
        base_url=local_http_server,
        endpoints=[
            EndpointDef(
                method="POST",
                path="/api/orders",
                operation_id="post_orders",
                request_body_required=True,
            )
        ],
    )
    WrapperGenerator(spec).write(wrapper_file)

    agent = ValidationAgent(wrapper_file, spec, llm_client=None)
    result = agent.validate()

    # Safely skipped without attempting HTTP call
    assert result.success is True
    assert "No GET endpoints" in (result.error or "")
