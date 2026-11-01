"""Unit tests for AST-based import scanning and distribution mapping."""

from __future__ import annotations

from pathlib import Path

from smartdevtool.deps.mapper import map_import_to_distribution, map_imports
from smartdevtool.deps.scanner import ImportScanner


def test_import_scanner_ast(tmp_path: Path):
    """Test AST scanning catches various import forms, excludes stdlib and local modules."""
    # Create local package directory without __init__.py (implicit namespace)
    local_pkg = tmp_path / "my_local_pkg"
    local_pkg.mkdir()
    (local_pkg / "helper.py").write_text("def helper(): pass", encoding="utf-8")

    # Create top-level local module
    (tmp_path / "local_mod.py").write_text("LOCAL_CONST = 1", encoding="utf-8")

    # Create test script with multi-line, aliased, and stdlib imports
    test_script = tmp_path / "main.py"
    test_script.write_text(
        """
import os
import sys
from pathlib import Path
import yaml as yml
from bs4 import BeautifulSoup as bs, NavigableString
import PIL.Image
import local_mod
from my_local_pkg import helper
from . import relative_mod  # should be ignored
from __future__ import annotations
""",
        encoding="utf-8",
    )

    scanner = ImportScanner(project_root=tmp_path)
    imports = scanner.scan()

    # Third party imports that MUST be found
    assert "yaml" in imports
    assert "bs4" in imports
    assert "PIL" in imports

    # Stdlib and local modules that MUST NOT be found
    assert "os" not in imports
    assert "sys" not in imports
    assert "pathlib" not in imports
    assert "__future__" not in imports
    assert "local_mod" not in imports
    assert "my_local_pkg" not in imports


def test_mapper_mismatches():
    """Verify common import-to-PyPI distribution mapping."""
    assert map_import_to_distribution("yaml") == "PyYAML"
    assert map_import_to_distribution("bs4") == "beautifulsoup4"
    assert map_import_to_distribution("PIL") == "Pillow"
    assert map_import_to_distribution("cv2") == "opencv-python"
    assert map_import_to_distribution("sklearn") == "scikit-learn"
    assert map_import_to_distribution("dotenv") == "python-dotenv"
    # Unmapped package maps to itself
    assert map_import_to_distribution("httpx") == "httpx"
    assert map_import_to_distribution("requests") == "requests"

    batch = map_imports({"yaml", "PIL", "httpx"})
    assert batch == {
        "PIL": "Pillow",
        "httpx": "httpx",
        "yaml": "PyYAML",
    }
