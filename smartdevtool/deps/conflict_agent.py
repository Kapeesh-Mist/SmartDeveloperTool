"""Autonomous bounded conflict resolution agent for Python dependencies.

Uses pip-compile's exit code as checkable ground truth.
Tries two strategies in order:
1. LLM proposal (if LLM is available)
2. Deterministic heuristic fallback (extracts project's own packages cited in conflict,
   unpinning most-implicated first, then remaining pins).
Terminates strictly within max_iters (default 8).
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from smartdevtool import ui
from smartdevtool.deps.resolver import DependencyResolver
from smartdevtool.llm.client import LLMClient
from smartdevtool.llm.prompts import DEPS_CONFLICT_SYSTEM_PROMPT, DEPS_CONFLICT_USER_TEMPLATE


@dataclass
class ResolutionAttempt:
    """Record of a single iteration attempt."""

    iteration: int
    strategy: str
    action_taken: str
    requirements: list[str]
    success: bool
    error_message: str | None = None


@dataclass
class ResolutionResult:
    """Final outcome of the conflict resolution agent."""

    success: bool
    final_requirements: list[str]
    lockfile_path: Path | None
    attempts: list[ResolutionAttempt] = field(default_factory=list)
    resolved_via: str | None = None
    error: str | None = None


def _normalize_pkg_name(req_str: str) -> str:
    """Extract base package name from a requirement specification."""
    # Match before any version specifier
    match = re.split(r"[=<>~!@; \t]", req_str.strip())
    return match[0].lower().replace("_", "-")


def _is_pinned(req_str: str) -> bool:
    """Return True if requirement has an exact or restrictive pin."""
    return any(op in req_str for op in ["==", "<=", "<", "~="])


class ConflictAgent:
    """Bounded agentic resolver loop."""

    def __init__(
        self,
        resolver: DependencyResolver | None = None,
        llm_client: LLMClient | None = None,
        max_iters: int = 8,
    ) -> None:
        self.resolver = resolver or DependencyResolver()
        self.llm_client = llm_client
        self.max_iters = max_iters

    def resolve(
        self,
        requirements: list[str],
        output_file: Path | str,
        work_dir: Path | str | None = None,
    ) -> ResolutionResult:
        """Execute bounded resolution loop."""
        output_path = Path(output_file).resolve()
        current_reqs = list(requirements)
        attempts: list[ResolutionAttempt] = []

        temp_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="sdt_deps_"))
        temp_dir.mkdir(parents=True, exist_ok=True)
        in_file = temp_dir / "requirements.in"

        # Initial compile check
        self._write_reqs(in_file, current_reqs)
        initial_result = self.resolver.compile(in_file, output_path)

        if initial_result.success:
            return ResolutionResult(
                success=True,
                final_requirements=current_reqs,
                lockfile_path=output_path,
                attempts=[
                    ResolutionAttempt(
                        iteration=0,
                        strategy="direct",
                        action_taken="Initial compile succeeded",
                        requirements=current_reqs,
                        success=True,
                    )
                ],
                resolved_via="direct",
            )

        if not initial_result.is_conflict:
            return ResolutionResult(
                success=False,
                final_requirements=current_reqs,
                lockfile_path=None,
                attempts=[
                    ResolutionAttempt(
                        iteration=0,
                        strategy="direct",
                        action_taken="Compile failed with non-conflict error",
                        requirements=current_reqs,
                        success=False,
                        error_message=initial_result.combined_output,
                    )
                ],
                error=f"Dependency failure is not a version conflict: {initial_result.combined_output[:300]}",
            )

        last_result = initial_result

        # Bounded loop
        for iteration in range(1, self.max_iters + 1):
            strategy_used = "heuristic"
            action_desc = ""
            new_reqs = list(current_reqs)

            # Strategy 1: LLM Proposal (if available)
            if self.llm_client and self.llm_client.available:
                llm_proposal = self._query_llm(current_reqs, last_result.combined_output)
                if llm_proposal:
                    applied, desc = self._apply_llm_proposal(new_reqs, llm_proposal)
                    if applied:
                        strategy_used = "llm"
                        action_desc = desc

            # Strategy 2: Deterministic Heuristic Fallback
            if not action_desc:
                strategy_used = "heuristic"
                applied, desc = self._apply_heuristic(new_reqs, last_result.combined_output)
                if not applied:
                    # Nothing left to unpin
                    attempts.append(
                        ResolutionAttempt(
                            iteration=iteration,
                            strategy="heuristic",
                            action_taken="No more pinned dependencies to relax",
                            requirements=current_reqs,
                            success=False,
                            error_message="Exhausted all unpinning possibilities",
                        )
                    )
                    break
                action_desc = desc

            ui.agent_attempt(iteration, self.max_iters, f"[{strategy_used.upper()}] {action_desc}")
            current_reqs = new_reqs

            self._write_reqs(in_file, current_reqs)
            compile_res = self.resolver.compile(in_file, output_path)

            attempts.append(
                ResolutionAttempt(
                    iteration=iteration,
                    strategy=strategy_used,
                    action_taken=action_desc,
                    requirements=list(current_reqs),
                    success=compile_res.success,
                    error_message=compile_res.combined_output if not compile_res.success else None,
                )
            )

            if compile_res.success:
                ui.success(f"Conflict resolved on attempt {iteration} via {strategy_used}!")
                return ResolutionResult(
                    success=True,
                    final_requirements=current_reqs,
                    lockfile_path=output_path,
                    attempts=attempts,
                    resolved_via=strategy_used,
                )

            last_result = compile_res
            if not last_result.is_conflict:
                return ResolutionResult(
                    success=False,
                    final_requirements=current_reqs,
                    lockfile_path=None,
                    attempts=attempts,
                    error=f"Non-conflict failure during resolution: {last_result.combined_output[:300]}",
                )

        ui.error(f"Resolution failed to converge within budget of {self.max_iters} iterations.")
        return ResolutionResult(
            success=False,
            final_requirements=current_reqs,
            lockfile_path=None,
            attempts=attempts,
            error=f"Exceeded max iterations ({self.max_iters}) without resolving conflict.",
        )

    def _write_reqs(self, path: Path, reqs: list[str]) -> None:
        """Write requirements list to file."""
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(f"{req.strip()}\n" for req in reqs)

    def _query_llm(self, reqs: list[str], error_text: str) -> dict[str, Any] | None:
        """Ask LLM to propose a constraint fix."""
        if not self.llm_client:
            return None
        prompt = DEPS_CONFLICT_USER_TEMPLATE.format(
            requirements="\n".join(reqs),
            error_text=error_text[:2000],
        )
        return self.llm_client.complete_json(DEPS_CONFLICT_SYSTEM_PROMPT, prompt)

    def _apply_llm_proposal(
        self, reqs: list[str], proposal: dict[str, Any]
    ) -> tuple[bool, str]:
        """Apply LLM proposed constraint modification."""
        action = proposal.get("action")
        target_pkg = proposal.get("package", "")
        norm_target = _normalize_pkg_name(target_pkg)
        new_constraint = proposal.get("new_constraint", "")

        for i, req in enumerate(reqs):
            if _normalize_pkg_name(req) == norm_target:
                if action == "unpin":
                    reqs[i] = norm_target
                    return True, f"LLM unpinned {norm_target}"
                elif action == "relax_pin" and new_constraint:
                    clean_constraint = new_constraint if new_constraint.startswith(("<", ">", "=", "~")) else f">={new_constraint}"
                    reqs[i] = f"{norm_target}{clean_constraint}"
                    return True, f"LLM relaxed {norm_target} to {reqs[i]}"
                elif action == "remove":
                    reqs.pop(i)
                    return True, f"LLM removed {norm_target}"
        return False, ""

    def _apply_heuristic(self, reqs: list[str], error_text: str) -> tuple[bool, str]:
        """Apply deterministic unpinning heuristic.

        Counts occurrences of project's pinned packages in pip's error text,
        unpins the most-implicated package first, or any remaining pinned package.
        """
        error_lower = error_text.lower()
        pinned_candidates: list[tuple[int, str, int]] = []  # (index, norm_name, count)

        for i, req in enumerate(reqs):
            if _is_pinned(req):
                norm_name = _normalize_pkg_name(req)
                count = error_lower.count(norm_name)
                pinned_candidates.append((i, norm_name, count))

        if not pinned_candidates:
            return False, ""

        # Sort by mention count descending (most implicated first)
        pinned_candidates.sort(key=lambda x: x[2], reverse=True)

        idx, pkg, count = pinned_candidates[0]
        old_req = reqs[idx]
        reqs[idx] = pkg
        return True, f"Unpinned {old_req} -> {pkg} (cited {count} times in conflict)"
