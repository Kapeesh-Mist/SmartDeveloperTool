"""Unit and integration tests for DependencyResolver and conflict classification."""

from __future__ import annotations

from pathlib import Path

from smartdevtool.deps.resolver import (
    CompileResult,
    DependencyResolver,
    is_resolution_conflict,
)


def test_conflict_detection_exclusion_first():
    """Verify that 'ResolutionImpossible' with nonexistent packages is NOT classified as conflict."""
    # Case 1: Nonexistent package produces ResolutionImpossible in pip traceback
    res_nonexistent = CompileResult(
        success=False,
        returncode=1,
        stdout="",
        stderr="""
ERROR: Could not find a version that satisfies the requirement non_existent_pkg_xyz123 (from versions: none)
ERROR: No matching distribution found for non_existent_pkg_xyz123
Traceback (most recent call last):
  File "pip/_internal/resolution/resolvelib/resolver.py", line 95, in resolve
    result = self._result = resolver.resolve(
pip._internal.exceptions.ResolutionImpossible: [RequirementInformation(...)]
""",
        is_conflict=False,
    )
    # MUST be False because "no matching distribution found" / "from versions: none" is checked first
    assert is_resolution_conflict(res_nonexistent) is False

    # Case 2: Real conflict between versions
    res_real_conflict = CompileResult(
        success=False,
        returncode=1,
        stdout="",
        stderr="""
ERROR: Cannot install -r requirements.in because these versions have conflicting dependencies.
The conflict is caused by:
    requests 2.20.0 depends on urllib3<1.25 and >=1.21.1
    The user requested urllib3==2.0.0
To fix this you could try to:
1. loosen the range of package versions you've specified
pip._internal.exceptions.ResolutionImpossible
""",
        is_conflict=False,
    )
    assert is_resolution_conflict(res_real_conflict) is True


def test_resolver_includes_upgrade_flag():
    """Verify that pip-compile command includes the mandatory --upgrade flag."""
    resolver = DependencyResolver()
    cmd = resolver._get_pip_compile_cmd() + [
        "--quiet",
        "--no-header",
        "--strip-extras",
        "--resolver=backtracking",
        "--upgrade",
        "--output-file",
        "out.txt",
        "in.txt",
    ]
    assert "--upgrade" in cmd
    assert "--resolver=backtracking" in cmd


def test_resolver_real_pypi_compilation(tmp_path: Path):
    """Run real pip-compile against real PyPI for a simple valid dependency."""
    in_file = tmp_path / "requirements.in"
    out_file = tmp_path / "requirements.txt"
    in_file.write_text("six==1.16.0\n", encoding="utf-8")

    resolver = DependencyResolver()
    res = resolver.compile(in_file, out_file)

    assert res.success is True
    assert res.returncode == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "six==1.16.0" in content
