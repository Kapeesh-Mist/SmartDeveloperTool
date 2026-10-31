# Smart DevTool

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-45%20passed%2C%201%20skipped-brightgreen.svg)]()

**Smart DevTool** is a production-grade CLI and Python library that automates API integration, dependency conflict resolution, and container environment synchronization.

---

## Key Features

### 1. Feature 1: Typed API Wrapper Generator (`smartdevtool wrapper`)
- **Multi-Input Ingestion**: Parse API specs from cURL commands, Postman collections (v2.1), HTTP Archive (HAR) captures, and OpenAPI / Swagger 2.0 & 3.x specifications.
- **Automated Auth Detection**: Automatically detects Bearer tokens, Basic Auth, API key headers (`X-API-Key`), query parameters, and custom headers.
- **Strict Secrets Discipline**: Ingested tokens and keys are never hardcoded into output code; they are transformed into secure environment variable lookups (`os.getenv`).
- **Jinja2 SDK Codegen & AST Validation**: Generates typed, idiomatic Python wrappers with `requests`, dataclass payloads, retry logic (`urllib3.util.Retry`), and docstrings. Every generated file is verified using Python's `ast.parse()` before writing to disk.
- **Bounded Self-Correcting Validation Agent**: Tests generated wrapper methods against endpoints. Upon HTTP 4xx/5xx or payload mismatch, an autonomous agent inspects response diagnostics and modifies parameters/serialization in up to `max_iters` loops.

### 2. Feature 2: Dependency Resolver & Autonomous Conflict Agent (`smartdevtool deps`)
- **AST Codebase Scanning**: Scans Python source trees using `ast.parse` with UTF-8 BOM tolerance to identify all imported third-party modules.
- **PyPI Canonical Mapping**: Accurately maps top-level module names to their canonical PyPI distribution names (e.g. `yaml` -> `PyYAML`, `PIL` -> `Pillow`, `dateutil` -> `python-dateutil`).
- **Real Backtracking Solver**: Runs `pip-compile` (`pip-tools`) under the hood to calculate locked, pinned dependencies with exact hashes.
- **Autonomous Conflict Agent**: When `pip-compile` throws `ResolutionImpossible`, an autonomous agent parses conflicting constraints, generates candidate fixes using LLM reasoning (or deterministic heuristic relaxation), verifies the fix via isolated dry-run, and rewrites `requirements.in` without manual intervention.

### 3. Feature 3: Docker Layer-Cached Sync Agent (`smartdevtool docker`)
- **Optimized Layer Caching**: Emits multi-stage Dockerfiles separating system packages (`apt-get`), dependencies (`requirements.txt`), and application code (`COPY . /app`) to maximize Docker layer cache hits.
- **SHA-256 Source Tree Fingerprinting**: Calculates hash digests across the codebase while respecting `.dockerignore` and `.gitignore` patterns.
- **Live Watchdog Sync**: Monitors file modification events. Code changes trigger instant container sync (`docker cp`), while dependency modifications trigger automated incremental image rebuilding.
- **Graceful Fallback**: Detects whether the Docker daemon is reachable. Degrades cleanly with actionable instructions when running offline or in environments without container runtimes.

---

## Architecture

```
                    +--------------------------------+
                    |       smartdevtool CLI         |
                    +---------------+----------------+
                                    |
          +-------------------------+-------------------------+
          |                         |                         |
          v                         v                         v
+-------------------+     +-------------------+     +-------------------+
|  Wrapper Gen (F1) |     |  Deps Solver (F2) |     | Docker Sync (F3)  |
|                   |     |                   |     |                   |
| - cURL/Postman/   |     | - AST Scanner     |     | - Dockerfile Gen  |
|   HAR/Doc Parsers |     | - PyPI Mapper     |     | - SHA-256 Hasher  |
| - Auth Detector   |     | - pip-compile     |     | - Watchdog Sync   |
| - Jinja2 Codegen  |     | - Conflict Agent  |     | - Docker Fallback |
| - Validation Agent|     | - Pip Installer   |     |                   |
+---------+---------+     +---------+---------+     +---------+---------+
          |                         |                         |
          +-------------------------+-------------------------+
                                    |
                    +---------------+----------------+
                    |          Shared Core           |
                    |                                |
                    | - config.py (Config Settings)  |
                    | - ui.py (Rich Console Helpers) |
                    | - manifest.py (State Store)    |
                    | - llm/client.py (NIM / Ollama) |
                    +--------------------------------+
```

---

## Installation

### Editable Developer Installation
```bash
# Clone the repository
git clone https://github.com/your-org/smartdevtool.git
cd smartdevtool

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

### Clean-Room Wheel Build & Install
```bash
# Build binary wheel and source distribution
python -m build

# Install wheel into isolated environment
pip install dist/smartdevtool-0.1.0-py3-none-any.whl
```

---

## CLI Reference & Usage

### 1. Dependency Management (`smartdevtool deps`)

#### Scan source code for imported third-party packages:
```bash
smartdevtool deps scan --src ./src
```

#### Compile and lock dependencies using backtracking:
```bash
smartdevtool deps resolve --in requirements.in --out requirements.txt
```

#### Scan, resolve, and install with autonomous conflict recovery:
```bash
smartdevtool deps install --src . --auto-resolve
```
*Options:*
- `--dry-run`: Output resolved lockfile without modifying current environment.
- `--no-llm`: Force deterministic heuristic relaxation instead of LLM agent.
- `-y`, `--yes`: Confirm installation prompts non-interactively.

---

### 2. API Wrapper Generation (`smartdevtool wrapper`)

#### Generate from cURL:
```bash
smartdevtool wrapper --curl "curl -X POST https://api.example.com/v1/users -H 'Authorization: Bearer my-token' -d '{\"name\":\"Alice\"}'" --name UserAPI --out ./generated_client.py
```

#### Generate from Postman collection:
```bash
smartdevtool wrapper --postman ./collection.json --name MyAPI --out ./client.py
```

#### Generate from HAR traffic capture:
```bash
smartdevtool wrapper --har ./traffic.har --name TrafficAPI --out ./client.py
```

#### Generate from OpenAPI / Swagger (JSON or YAML):
```bash
smartdevtool wrapper --doc ./openapi.yaml --name PetstoreAPI --out ./petstore.py
```

#### Bounded self-correcting validation:
```bash
smartdevtool wrapper --curl "curl http://localhost:8000/api" --test --max-iters 3
```

---

### 3. Docker Sync (`smartdevtool docker`)

#### Generate an optimized, layer-cached Dockerfile:
```bash
smartdevtool docker build --python-version 3.11 --out Dockerfile
```

#### Live file synchronization and hot reload:
```bash
smartdevtool docker sync --container my-container --watch ./src
```

---

## Verified Terminal Outputs

### 1. PyPI Backtracking & Conflict Agent Resolution
When pins conflict (e.g. `requests==2.20.0` requiring `urllib3<1.25`, but `urllib3==2.0.0` pinned):
```text
> smartdevtool deps install --src ./test_conflict --no-llm -y
[!] pip-compile failed with ResolutionImpossible
[!] Conflict Agent activated (mode: deterministic heuristic)
[!] Detected conflicting packages: requests, urllib3
[!] Relaxing pin: requests==2.20.0 -> requests>=2.20.0
[!] Relaxing pin: urllib3==2.0.0 -> urllib3>=2.0.0
[OK] Re-resolving dependencies with relaxed constraints...
[OK] Resolution successful! Locked 5 packages in requirements.txt:
     - certifi==2024.8.30
     - charset-normalizer==3.3.2
     - idna==3.10
     - requests==2.32.3
     - urllib3==2.3.0
[OK] Dependencies installed successfully.
```

### 2. API Wrapper Codegen & AST Validation
```text
> smartdevtool wrapper --curl "curl -X POST https://api.stripe.com/v1/charges -u sk_test_123: -d amount=2000" --name StripeAPI
[OK] Ingested 1 endpoint from cURL input
[OK] Detected Basic Auth credentials (sk_test_123: -> STRIPE_API_API_KEY)
[OK] AST validation passed: generated code is syntactically valid Python
[OK] SDK wrapper written to ./stripe_api.py
```

### 3. Docker Layer Cache Optimization
```dockerfile
# Generated by Smart DevTool
FROM python:3.11-slim

WORKDIR /app

# Step 1: Install system dependencies (cached)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Step 2: Install Python dependencies (cached until requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 3: Copy application source code (invalidates only on code change)
COPY . /app

CMD ["python", "main.py"]
```

---

## Real Bugs Caught & Fixed During Verification

During development and verification across clean-room environments, multiple edge cases and platform bugs were discovered and addressed:

| Component | Root Cause | Engineering Solution |
| :--- | :--- | :--- |
| **Console UI (`ui.py`)** | Rich unicode glyphs (`❯`, box-borders) failed with `UnicodeEncodeError: 'charmap'` on Windows cp1252 consoles. | Implemented ASCII/Windows-safe glyph fallback (`>`, `[OK]`, `[X]`) and enabled `Console(safe_box=True)`. |
| **AST Scanner (`scanner.py`)** | PowerShell files saved with UTF-8 BOM (`\xef\xbb\xbf`) caused `ast.parse` to crash with `SyntaxError: invalid non-printable character U+FEFF`. | Configured file reading in `scanner.py` with `encoding="utf-8-sig"`. |
| **Wheel Packaging (`pyproject.toml`)** | `wrapper_template.py.jinja` was omitted from binary wheels by default setuptools packaging rules. | Added package-data directive `[tool.setuptools.package-data] "smartdevtool.wrapper" = ["templates/*.jinja"]`. |
| **Clean-Room Virtualenv** | `doc_input.py` imported `yaml`, which failed in fresh clean-room virtualenvs missing PyYAML. | Added `pyyaml>=6.0.0` directly to `dependencies` list in `pyproject.toml`. |
| **Pip Resolver (`resolver.py`)** | Pip throws `ResolutionImpossible` even for nonexistent distributions (e.g., typos in package names). | Added pre-checks for `no matching distribution found` to fail fast with diagnostic errors. |

---

## Test Suite

The test suite runs offline without external dependencies or live network access:
```bash
pytest -v
```

Output:
```text
tests/test_conflict_agent.py ...                                         [  6%]
tests/test_core.py .....                                                 [ 17%]
tests/test_deps_cli.py ..                                                [ 21%]
tests/test_deps_resolver.py ...                                          [ 28%]
tests/test_deps_scanner.py ..                                            [ 32%]
tests/test_docker_change_detector.py ...                                 [ 39%]
tests/test_docker_cli.py ..                                              [ 43%]
tests/test_docker_dockerfile_gen.py ....                                 [ 52%]
tests/test_docker_sync.py ....s                                          [ 63%]
tests/test_wrapper_cli.py ....                                           [ 71%]
tests/test_wrapper_codegen.py ....                                       [ 80%]
tests/test_wrapper_parsers.py .....                                      [ 91%]
tests/test_wrapper_validation.py ....                                    [100%]

======================= 45 passed, 1 skipped in 33.87s ========================
```

---

