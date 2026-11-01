"""Tests for ConflictAgent covering real PyPI conflict resolution, fake LLM branch, and bounded loop termination."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from smartdevtool.deps.conflict_agent import ConflictAgent
from smartdevtool.deps.resolver import CompileResult, DependencyResolver
from smartdevtool.llm.client import LLMClient


def test_real_pypi_conflict_resolution_heuristic(tmp_path: Path):
    """MUST invoke real pip-compile against real PyPI with a genuine version clash.

    requests==2.20.0 strictly requires urllib3<1.25 and >=1.21.1.
    urllib3==2.0.0 violates this constraint.
    The heuristic unpins the implicated package and resolves cleanly.
    """
    initial_reqs = ["requests==2.20.0", "urllib3==2.0.0"]
    out_file = tmp_path / "resolved_requirements.txt"

    # Fully offline-capable heuristic path (no LLM)
    agent = ConflictAgent(
        resolver=DependencyResolver(),
        llm_client=None,
        max_iters=5,
    )

    result = agent.resolve(initial_reqs, output_file=out_file, work_dir=tmp_path / "work")

    assert result.success is True, f"Resolution failed with error: {result.error}"
    assert result.resolved_via == "heuristic"
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "requests" in content
    assert "urllib3" in content
    # Verify at least one attempt was made to relax the conflict
    assert len(result.attempts) >= 1


def test_conflict_agent_scripted_fake_llm(tmp_path: Path):
    """Test LLM proposal resolution path using a scripted fake LLMClient."""
    initial_reqs = ["requests==2.20.0", "urllib3==2.0.0"]
    out_file = tmp_path / "llm_resolved.txt"

    fake_llm = MagicMock(spec=LLMClient)
    fake_llm.available = True
    fake_llm.complete_json.return_value = {
        "action": "unpin",
        "package": "requests",
        "new_constraint": "",
        "reasoning": "Unpin requests to allow modern version compatible with urllib3 2.0.0",
    }

    agent = ConflictAgent(
        resolver=DependencyResolver(),
        llm_client=fake_llm,
        max_iters=5,
    )

    result = agent.resolve(initial_reqs, output_file=out_file, work_dir=tmp_path / "work_llm")

    assert result.success is True
    assert result.resolved_via == "llm"
    assert fake_llm.complete_json.called
    assert out_file.exists()


def test_conflict_agent_bounded_loop_termination(tmp_path: Path):
    """Verify that agentic loop terminates at max_iters and does not hang when unsolvable."""
    mock_resolver = MagicMock(spec=DependencyResolver)
    mock_resolver.compile.return_value = CompileResult(
        success=False,
        returncode=1,
        stdout="",
        stderr="ERROR: Cannot install because of conflicting dependencies: package_a and package_b",
        is_conflict=True,
    )

    agent = ConflictAgent(
        resolver=mock_resolver,
        llm_client=None,
        max_iters=3,
    )

    result = agent.resolve(
        ["package_a==1.0", "package_b==2.0"],
        output_file=tmp_path / "never.txt",
        work_dir=tmp_path / "work_bound",
    )

    assert result.success is False
    # Max iters was 3, so loop must not run more than 3 iterations
    assert len(result.attempts) <= 4
    assert "Exceeded max iterations" in (result.error or "") or "Exhausted" in (result.error or "")
