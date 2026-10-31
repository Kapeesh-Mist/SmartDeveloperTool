"""Mapping table from Python import module names to PyPI distribution names.

Handles common mismatches where the import name differs from the package name installed via pip.
Anything not in the mapping table maps to itself.
"""

from __future__ import annotations

IMPORT_TO_DISTRIBUTION: dict[str, str] = {
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "magic": "python-magic",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "jose": "python-jose",
    "jwt": "PyJWT",
    "serial": "pyserial",
    "usb": "pyusb",
    "OpenSSL": "pyOpenSSL",
    "Crypto": "pycryptodome",
    "websocket": "websocket-client",
    "attr": "attrs",
    "fitz": "PyMuPDF",
    "git": "GitPython",
    "dj_database_url": "dj-database-url",
    "rest_framework": "djangorestframework",
}


def map_import_to_distribution(import_name: str) -> str:
    """Map a Python module import name to its canonical PyPI distribution name.

    If the import name is not in the mismatch dictionary, return the import name unchanged.
    """
    return IMPORT_TO_DISTRIBUTION.get(import_name, import_name)


def map_imports(import_names: set[str] | list[str]) -> dict[str, str]:
    """Map a collection of import names to a dict of {import_name: distribution_name}."""
    return {imp: map_import_to_distribution(imp) for imp in sorted(import_names)}
