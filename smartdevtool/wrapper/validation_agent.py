"""Agentic validation loop for generated API SDK wrappers.

Ground truth: does the real HTTP call succeed (<400)?
Strict safety boundaries:
1. ONLY GET endpoints are auto-validated. Mutating endpoints (POST/PUT/PATCH/DELETE) are never touched.
2. Only modifies the single target wrapper file being validated.
3. Exits immediately on 403 or 5xx without attempting fixes.
4. On 401: tries LLM proposal if available, otherwise deterministic heuristic swapping
   (Authorization: Bearer <-> X-Api-Key).
5. Bounded by max_iters (default 6).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from smartdevtool import ui
from smartdevtool.llm.client import LLMClient
from smartdevtool.llm.prompts import (
    WRAPPER_AUTH_FIX_SYSTEM_PROMPT,
    WRAPPER_AUTH_FIX_USER_TEMPLATE,
)
from smartdevtool.wrapper.codegen import WrapperGenerator
from smartdevtool.wrapper.spec import EndpointDef, EndpointSpec


@dataclass
class ValidationAttempt:
    """Record of an automated validation attempt."""

    iteration: int
    strategy: str
    action_taken: str
    status_code: int | None
    success: bool
    error_message: str | None = None


@dataclass
class ValidationResult:
    """Final outcome of the wrapper validation agent."""

    success: bool
    wrapper_path: Path
    tested_endpoint: str | None = None
    status_code: int | None = None
    attempts: list[ValidationAttempt] = field(default_factory=list)
    resolved_via: str | None = None
    error: str | None = None


class ValidationAgent:
    """Bounded agentic validation loop for Python SDK wrappers."""

    def __init__(
        self,
        wrapper_file: Path | str,
        spec: EndpointSpec,
        llm_client: LLMClient | None = None,
        max_iters: int = 6,
    ) -> None:
        self.wrapper_path = Path(wrapper_file).resolve()
        self.spec = spec
        self.llm_client = llm_client
        self.max_iters = max_iters

    def _load_and_run(
        self, endpoint: EndpointDef, test_token: str
    ) -> tuple[int | None, str]:
        """Dynamically load wrapper class and invoke the target GET endpoint."""
        try:
            spec_mod = importlib.util.spec_from_file_location(
                f"wrapper_val_{endpoint.operation_id}", self.wrapper_path
            )
            if not spec_mod or not spec_mod.loader:
                return None, "Failed to create module spec"

            mod = importlib.util.module_from_spec(spec_mod)
            spec_mod.loader.exec_module(mod)

            # Find client class
            client_cls = getattr(mod, self.spec.title, None)
            if not client_cls:
                for attr_name in dir(mod):
                    obj = getattr(mod, attr_name)
                    if isinstance(obj, type) and hasattr(obj, "close"):
                        client_cls = obj
                        break

            if not client_cls:
                return None, "No SDK client class found in generated file"

            with client_cls(
                base_url=self.spec.base_url,
                api_key=test_token,
                timeout=10.0,
            ) as client:
                method_func = getattr(client, endpoint.operation_id, None)
                if not method_func:
                    return None, f"Method {endpoint.operation_id} not found on client"
                resp = method_func()
                return resp.status_code, resp.text[:500]
        except Exception as exc:
            return None, str(exc)

    def validate(self, test_token: str = "test-token") -> ValidationResult:
        """Execute bounded validation loop."""
        # Critical Safety Scope: ONLY GET endpoints are validated
        get_endpoints = [ep for ep in self.spec.endpoints if ep.method == "GET"]
        if not get_endpoints:
            ui.warn("No GET endpoints found. Skipping automated validation (mutating endpoints excluded for safety).")
            return ValidationResult(
                success=True,
                wrapper_path=self.wrapper_path,
                error="No GET endpoints to validate",
            )

        target_ep = get_endpoints[0]
        target_name = f"GET {target_ep.path}"
        ui.step(f"Validating wrapper against safe GET endpoint: {target_name}")

        attempts: list[ValidationAttempt] = []

        # Initial call
        status_code, response_body = self._load_and_run(target_ep, test_token)

        if status_code is not None and status_code < 400:
            ui.success(f"Wrapper validated successfully on initial check (HTTP {status_code})")
            return ValidationResult(
                success=True,
                wrapper_path=self.wrapper_path,
                tested_endpoint=target_name,
                status_code=status_code,
                attempts=[
                    ValidationAttempt(
                        iteration=0,
                        strategy="direct",
                        action_taken="Initial call succeeded",
                        status_code=status_code,
                        success=True,
                    )
                ],
                resolved_via="direct",
            )

        # Immediate abort on 403 or 5xx: structurally unfixable by header convention tweaks
        if status_code == 403 or (status_code is not None and status_code >= 500):
            ui.error(f"Validation failed with HTTP {status_code}. Giving up immediately (not a fixable auth convention issue).")
            return ValidationResult(
                success=False,
                wrapper_path=self.wrapper_path,
                tested_endpoint=target_name,
                status_code=status_code,
                attempts=[
                    ValidationAttempt(
                        iteration=0,
                        strategy="direct",
                        action_taken=f"Failed with HTTP {status_code}",
                        status_code=status_code,
                        success=False,
                        error_message="Structurally unfixable error (403/5xx)",
                    )
                ],
                error=f"Unfixable HTTP status: {status_code}",
            )

        # Bounded loop for 401 errors
        for iteration in range(1, self.max_iters + 1):
            strategy_used = "heuristic"
            action_desc = ""

            # Strategy 1: LLM Proposal (if available)
            if self.llm_client and self.llm_client.available:
                llm_proposal = self._query_llm(target_ep, status_code, response_body)
                if llm_proposal and llm_proposal.get("action") != "give_up":
                    applied, desc = self._apply_llm_proposal(llm_proposal)
                    if applied:
                        strategy_used = "llm"
                        action_desc = desc

            # Strategy 2: Deterministic Heuristic Fallback
            if not action_desc:
                strategy_used = "heuristic"
                applied, desc = self._apply_heuristic()
                if not applied:
                    break
                action_desc = desc

            ui.agent_attempt(iteration, self.max_iters, f"[{strategy_used.upper()}] {action_desc}")

            # Re-generate ONLY the target wrapper file
            generator = WrapperGenerator(self.spec)
            generator.write(self.wrapper_path)

            status_code, response_body = self._load_and_run(target_ep, test_token)
            success = status_code is not None and status_code < 400

            attempts.append(
                ValidationAttempt(
                    iteration=iteration,
                    strategy=strategy_used,
                    action_taken=action_desc,
                    status_code=status_code,
                    success=success,
                    error_message=response_body if not success else None,
                )
            )

            if success:
                ui.success(f"Wrapper self-corrected and passed on attempt {iteration} via {strategy_used} (HTTP {status_code})")
                return ValidationResult(
                    success=True,
                    wrapper_path=self.wrapper_path,
                    tested_endpoint=target_name,
                    status_code=status_code,
                    attempts=attempts,
                    resolved_via=strategy_used,
                )

            # Give up immediately if status changed to 403 or 5xx
            if status_code == 403 or (status_code is not None and status_code >= 500):
                ui.error(f"Encountered HTTP {status_code} during validation. Terminating loop.")
                break

        ui.error(f"Validation failed to converge after {len(attempts)} attempts.")
        return ValidationResult(
            success=False,
            wrapper_path=self.wrapper_path,
            tested_endpoint=target_name,
            status_code=status_code,
            attempts=attempts,
            error=f"Validation failed to converge within {self.max_iters} iterations",
        )

    def _query_llm(
        self, endpoint: EndpointDef, status_code: int | None, response_body: str
    ) -> dict[str, Any] | None:
        """Ask LLM to suggest auth header convention correction."""
        if not self.llm_client:
            return None
        prompt = WRAPPER_AUTH_FIX_USER_TEMPLATE.format(
            url=f"{self.spec.base_url}{endpoint.path}",
            method=endpoint.method,
            status_code=status_code or "Unknown",
            response_body=response_body[:500],
            header_name=self.spec.auth.header_name,
            scheme=self.spec.auth.scheme,
        )
        return self.llm_client.complete_json(WRAPPER_AUTH_FIX_SYSTEM_PROMPT, prompt)

    def _apply_llm_proposal(self, proposal: dict[str, Any]) -> tuple[bool, str]:
        """Apply LLM's suggested auth change."""
        action = proposal.get("action")
        header_name = proposal.get("header_name", "")
        scheme = proposal.get("scheme", "")

        if action in ("change_auth_header", "change_auth_scheme"):
            self.spec.auth.header_name = header_name or self.spec.auth.header_name
            self.spec.auth.scheme = scheme
            self.spec.auth.type = "jwt" if scheme.lower() == "bearer" else "api_key"
            return True, f"LLM changed auth header to '{self.spec.auth.header_name}' (scheme='{scheme}')"
        return False, ""

    def _apply_heuristic(self) -> tuple[bool, str]:
        """Deterministic heuristic fallback: swap between Authorization: Bearer and X-Api-Key."""
        current_header = (self.spec.auth.header_name or "").lower()

        if "authorization" in current_header:
            # Swap to X-Api-Key
            self.spec.auth.type = "api_key"
            self.spec.auth.header_name = "X-Api-Key"
            self.spec.auth.scheme = ""
            return True, "Swapped auth header convention from 'Authorization: Bearer' to 'X-Api-Key'"
        else:
            # Swap to Authorization: Bearer
            self.spec.auth.type = "jwt"
            self.spec.auth.header_name = "Authorization"
            self.spec.auth.scheme = "Bearer"
            return True, "Swapped auth header convention from 'X-Api-Key' to 'Authorization: Bearer'"
