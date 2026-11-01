"""Pure, offline unit tests for ChangeDetector source tree hashing and drift detection."""

from __future__ import annotations

from pathlib import Path
from smartdevtool.docker.change_detector import ChangeDetector


def test_change_detector_fingerprint_deterministic(tmp_path: Path):
    """Verify hash is identical for identical files and changes when content is mutated."""
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "utils.py").write_text("def add(a, b): return a + b", encoding="utf-8")

    detector = ChangeDetector(tmp_path)
    hash1, files1 = detector.compute_fingerprint()

    # Re-computing without changes must produce byte-identical hash
    hash2, files2 = detector.compute_fingerprint()
    assert hash1 == hash2
    assert files1 == files2

    # Mutate a file
    (tmp_path / "app.py").write_text("print('hello world')", encoding="utf-8")
    hash3, _ = detector.compute_fingerprint()
    assert hash3 != hash1, "Fingerprint must change when file content changes"


def test_change_detector_drift_detection(tmp_path: Path):
    """Verify drift detection against recorded baseline hash."""
    (tmp_path / "main.py").write_text("API_VERSION = 1", encoding="utf-8")

    detector = ChangeDetector(tmp_path)
    init_hash, _ = detector.compute_fingerprint()

    # Baseline matches: no drift
    is_drift, current_hash, _ = detector.detect_drift(last_build_hash=init_hash)
    assert is_drift is False
    assert current_hash == init_hash

    # Add a new file: drift must be detected
    (tmp_path / "new_module.py").write_text("NEW_VAR = 2", encoding="utf-8")
    is_drift2, new_hash, _ = detector.detect_drift(last_build_hash=init_hash)
    assert is_drift2 is True
    assert new_hash != init_hash


def test_change_detector_ignores_untracked_dirs(tmp_path: Path):
    """Verify ignored directories (.git, __pycache__, dist) do not alter the fingerprint."""
    (tmp_path / "main.py").write_text("x = 1", encoding="utf-8")
    detector = ChangeDetector(tmp_path)
    base_hash, _ = detector.compute_fingerprint()

    # Create ignored directories and files
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "main.cpython-311.pyc").write_bytes(b"\x00\x01\x02")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")

    new_hash, _ = detector.compute_fingerprint()
    assert new_hash == base_hash, "Ignored directories must not affect source tree hash"
