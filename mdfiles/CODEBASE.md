# Smart DevTool — Codebase Architecture & File Reference

This document provides a complete breakdown of every folder and file in the **Smart DevTool** repository, explaining what each folder does, what each individual file contributes, and how they connect together to deliver the tool's 3 primary features.

---

## 🗺️ High-Level Architectural Map

```
smartdevtoolv1/
├── pyproject.toml / requirements.txt / .env.example
├── smartdevtool/
│   ├── [CORE FOUNDATION]       (cli.py, config.py, ui.py, manifest.py)
│   ├── llm/                    (LLM Fallback & Prompt Management)
│   ├── wrapper/                (FEATURE 1: API SDK Generator)
│   │   ├── inputs/             (Raw Source Parsers)
│   │   └── templates/          (Jinja2 Code Templates)
│   ├── deps/                   (FEATURE 2: Dependency & Conflict Resolver)
│   └── docker/                 (FEATURE 3: Docker Generator & Live Sync)
└── tests/                      (46 Unit & Integration Tests)
```

---

## 📁 1. Root Configuration Files

| File | Purpose & Contribution |
| :--- | :--- |
| [`pyproject.toml`](file:///d:/Project/smartdevtoolv1/pyproject.toml) | **Project Definition & CLI Packaging**: Defines `smartdevtool` as an installable Python package, lists core runtime dependencies (`typer`, `rich`, `pydantic`, `jinja2`, `pip-tools`, `watchdog`), and maps the terminal command `smartdevtool` to [`smartdevtool.cli:app`](file:///d:/Project/smartdevtoolv1/smartdevtool/cli.py). |
| [`requirements.txt`](file:///d:/Project/smartdevtoolv1/requirements.txt) | **Unpinned Dependencies**: Quick-install reference for basic requirements before the tool's own resolver is used. |
| [`.env.example`](file:///d:/Project/smartdevtoolv1/.env.example) | **Environment Configuration Blueprint**: Outlines environment variables for the LLM fallback engine (`NVIDIA_API_KEY`, `OLLAMA_HOST`) and self-correction loop bounds (`MAX_ITERS_VALIDATION=6`, `MAX_ITERS_CONFLICT=8`). |

---

## 📁 2. Core Package (`smartdevtool/`)

The shared engine that coordinates CLI interaction, logging, configuration, and session persistence across all 3 features.

### Files in this folder:
- **[`smartdevtool/cli.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/cli.py)** *(CLI Entrypoint & Command Dispatcher)*
  - **Contribution**: Provides the Typer-based terminal UI and command tree (`smartdevtool wrap`, `smartdevtool deps`, `smartdevtool docker`). Parses CLI flags (such as `--no-llm`, `--output`, `--port`, `--dry-run`), coordinates progress bars, and routes commands to their respective submodules.
- **[`smartdevtool/config.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/config.py)** *(Settings & Global State)*
  - **Contribution**: Holds the `Config` dataclass which reads and manages application runtime settings from environment variables and `.env` files with safe defaults.
- **[`smartdevtool/ui.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/ui.py)** *(Console Rendering & Cross-Platform Formatting)*
  - **Contribution**: Wraps the `rich` library to print styled boxes, diff views, spinners, and tables. Specifically configured with ASCII glyph fallbacks to prevent rendering glitches on standard Windows PowerShell/CMD terminals.
- **[`smartdevtool/manifest.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/manifest.py)** *(Local State Persistence)*
  - **Contribution**: Manages `.smartdevtool/manifest.json`. Records generated SDK specs, resolved dependency locks, and Docker state across runs so the tool can track changes incrementally.

---

## 📁 3. AI & Prompt Engine (`smartdevtool/llm/`)

Provides intelligent fallback handling when raw deterministic parsers encounter messy prose, ambiguous documentation, or unsolvable package conflicts.

### Files in this folder:
- **[`smartdevtool/llm/client.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/llm/client.py)** *(Fallback Client Chain)*
  - **Contribution**: Implements a graceful fallback chain:
    1. **NVIDIA NIM Cloud** (if `NVIDIA_API_KEY` is present)
    2. **Ollama Local** (if running locally at `localhost:11434`)
    3. **None / Disabled** (works 100% offline deterministically if `--no-llm` is set)
- **[`smartdevtool/llm/prompts.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/llm/prompts.py)** *(Structured System Prompts)*
  - **Contribution**: Contains structured JSON-schema prompts for doc parsing, HTTP self-correction, package conflict resolution, and Docker base image selection.

---

## 📁 4. Feature 1: API Wrapper Generator (`smartdevtool/wrapper/`)

Generates complete, production-ready, typed Python SDKs (like `githubapiclient_sdk.py`) from cURL commands, Postman collections, HAR traffic files, and OpenAPI docs.

### Pipeline Flow:
```mermaid
flowchart LR
    Input[cURL / Postman / HAR / Docs] --> InputsFolder[inputs/*.py Parsers]
    InputsFolder --> Auth[auth_detector.py]
    Auth --> Norm[normalizer.py]
    Norm --> Spec[spec.py Dataclasses]
    Spec --> Jinja[codegen.py + wrapper_template.py.jinja]
    Jinja --> ASTCheck[ast.parse Validation]
    ASTCheck --> Agent[validation_agent.py (HTTP Live Test)]
    Agent --> OutputFile[Generated Python SDK]
```

### Files in this folder:
- **[`smartdevtool/wrapper/spec.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/spec.py)** *(The Central Contract)*
  - **Contribution**: Defines the core schema (`EndpointSpec`, `EndpointDef`, `ParamDef`, `AuthInfo`) that all input parsers must translate into.
- **[`smartdevtool/wrapper/auth_detector.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/auth_detector.py)** *(Auth Strategy Classifier)*
  - **Contribution**: Inspects headers, query parameters, and security schemes to classify authentication (Bearer Token, API Key, Basic Auth, OAuth2) and generates standard environment variable names (e.g., `GITHUB_API_KEY`).
- **[`smartdevtool/wrapper/normalizer.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/normalizer.py)** *(Deduplication & Path Normalizer)*
  - **Contribution**: Merges endpoint definitions from multiple inputs, cleans up route parameters (converting `{user_id}` or `:user_id` to pythonic names), and prevents duplicate method declarations.
- **[`smartdevtool/wrapper/codegen.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/codegen.py)** *(Code Generator & Syntax Guardian)*
  - **Contribution**: Feeds the normalized spec into the Jinja2 template to render the Python SDK. **Crucially, it runs `ast.parse()` on the generated code** to guarantee zero syntax errors before saving.
- **[`smartdevtool/wrapper/llm_structurer.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/llm_structurer.py)** *(Prose Document Parser)*
  - **Contribution**: Uses the LLM fallback to parse unformatted markdown or messy HTML API documentation into an `EndpointSpec` when standard Swagger/OpenAPI schemas are absent.
- **[`smartdevtool/wrapper/validation_agent.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/validation_agent.py)** *(Self-Correction Loop)*
  - **Contribution**: Performs bounded live HTTP tests against `GET` endpoints. If the API returns a 4xx error (such as a missing query param or invalid header), the agent diagnoses the issue and automatically adjusts the generated SDK.

### Subfolder: `smartdevtool/wrapper/inputs/` *(Parsers)*
- **[`inputs/curl_input.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/inputs/curl_input.py)**: Parses raw `curl ...` command strings using `shlex` to extract HTTP methods, URLs, query params, headers, and request bodies.
- **[`inputs/postman_input.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/inputs/postman_input.py)**: Traverses Postman Collection v2.1 JSON trees (including nested subfolders) to extract complete API definitions.
- **[`inputs/har_input.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/inputs/har_input.py)**: Parses browser network traffic files (`.har`), automatically filtering out noise, static assets (`.png`, `.js`), and analytics trackers.
- **[`inputs/doc_input.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/inputs/doc_input.py)**: Ingests OpenAPI 3.0+ and Swagger 2.0 specs (JSON/YAML) into standardized `EndpointSpec` models.

### Subfolder: `smartdevtool/wrapper/templates/`
- **[`templates/wrapper_template.py.jinja`](file:///d:/Project/smartdevtoolv1/smartdevtool/wrapper/templates/wrapper_template.py.jinja)**: The Jinja2 template that produces the Python class with type hints, `httpx` async/sync sessions, exponential backoff retries, and rate limiting.

---

## 📁 5. Feature 2: Dependency & Conflict Resolver (`smartdevtool/deps/`)

Scans source code for imports, maps them to official PyPI package names, generates reproducible lockfiles, and autonomously resolves version conflicts.

### Pipeline Flow:
```mermaid
flowchart LR
    Code[Source Files] --> Scan[scanner.py (AST Imports)]
    Scan --> Map[mapper.py (Module -> PyPI)]
    Map --> Resolve[resolver.py (pip-compile)]
    Resolve -- Conflict Encountered --> ConflictAgent[conflict_agent.py (LLM + Heuristic Unpin)]
    ConflictAgent --> Resolve
    Resolve -- Success --> Lockfile[requirements.lock]
    Lockfile --> Install[installer.py (pip install)]
```

### Files in this folder:
- **[`smartdevtool/deps/scanner.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/deps/scanner.py)** *(Codebase Import Scanner)*
  - **Contribution**: Walks the project directory using Python's `ast` (Abstract Syntax Tree) module to find all `import xyz` and `from xyz import ...` statements. Handles UTF-8 BOM encoding safely for Windows files.
- **[`smartdevtool/deps/mapper.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/deps/mapper.py)** *(PyPI Canonical Mapper)*
  - **Contribution**: Bridges the gap between import names and PyPI distribution names (e.g., `import cv2` -> `opencv-python`, `import yaml` -> `PyYAML`, `import PIL` -> `Pillow`). Filters out Python standard library modules.
- **[`smartdevtool/deps/resolver.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/deps/resolver.py)** *(Lockfile Generator)*
  - **Contribution**: Wraps `pip-compile` (`pip-tools`) in a subprocess. When a dependency incompatibility occurs, it intercepts the error and classifies the exact conflicting packages and version bounds.
- **[`smartdevtool/deps/conflict_agent.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/deps/conflict_agent.py)** *(Self-Healing Conflict Resolver)*
  - **Contribution**: If `pip-compile` fails due to conflicting pins (e.g., Package A needs `urllib3<2.0` and Package B needs `urllib3>=2.0`), this agent unpins/relaxes constraints step-by-step (up to 8 iterations) until a clean dependency solution is found.
- **[`smartdevtool/deps/installer.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/deps/installer.py)** *(Subprocess Installer)*
  - **Contribution**: Safely installs the verified lockfile into the target virtual environment with progress reporting and rollback capabilities.

---

## 📁 6. Feature 3: Docker Generator & Live Sync (`smartdevtool/docker/`)

Creates optimized, layer-cached production `Dockerfile` configurations and monitors the workspace for real-time rebuilds and container synchronization.

### Pipeline Flow:
```mermaid
flowchart LR
    Project[Project Files + Lockfile] --> Gen[dockerfile_gen.py]
    Gen --> Dockerfile[Dockerfile + .dockerignore]
    Dockerfile --> Build[build.py (docker build CLI)]
    SourceCode[File Changes] --> Detector[change_detector.py (SHA-256)]
    Detector --> Sync[sync_agent.py (watchdog)]
    Sync -- Significant Drift --> Build
```

### Files in this folder:
- **[`smartdevtool/docker/dockerfile_gen.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/docker/dockerfile_gen.py)** *(Dockerfile Generator)*
  - **Contribution**: Inspects Python version and dependencies to generate multi-stage or layer-cached `Dockerfile` and `.dockerignore` files (copying `requirements.lock` first to maximize Docker build caching).
- **[`smartdevtool/docker/change_detector.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/docker/change_detector.py)** *(Source Tree Fingerprinter)*
  - **Contribution**: Calculates SHA-256 hashes of source files to detect code drift and categorize changes (code-only change vs. dependency change).
- **[`smartdevtool/docker/build.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/docker/build.py)** *(Docker Subprocess Wrapper)*
  - **Contribution**: Interfaces with the local Docker CLI daemon. Verifies if Docker is running, triggers builds, streams logs, and handles build errors.
- **[`smartdevtool/docker/sync_agent.py`](file:///d:/Project/smartdevtoolv1/smartdevtool/docker/sync_agent.py)** *(Continuous File Watcher)*
  - **Contribution**: Uses `watchdog` to monitor the filesystem in real time. Hot-reloads running containers or triggers background rebuilds when files are modified.

---

## 📁 7. Test Suite (`tests/`)

Contains 46 comprehensive unit and integration tests verifying every feature component.

| Test File | Target Module Tested | Feature Verified |
| :--- | :--- | :--- |
| [`tests/test_core.py`](file:///d:/Project/smartdevtoolv1/tests/test_core.py) | `smartdevtool/config.py`, `ui.py`, `manifest.py` | Core Foundation |
| [`tests/test_wrapper_spec.py`](file:///d:/Project/smartdevtoolv1/tests/test_wrapper_spec.py) | `smartdevtool/wrapper/spec.py` | Feature 1: Data models |
| [`tests/test_wrapper_curl.py`](file:///d:/Project/smartdevtoolv1/tests/test_wrapper_curl.py) | `smartdevtool/wrapper/inputs/curl_input.py` | Feature 1: cURL parsing |
| [`tests/test_wrapper_postman.py`](file:///d:/Project/smartdevtoolv1/tests/test_wrapper_postman.py) | `smartdevtool/wrapper/inputs/postman_input.py` | Feature 1: Postman parsing |
| [`tests/test_wrapper_har.py`](file:///d:/Project/smartdevtoolv1/tests/test_wrapper_har.py) | `smartdevtool/wrapper/inputs/har_input.py` | Feature 1: HAR parsing |
| [`tests/test_wrapper_codegen.py`](file:///d:/Project/smartdevtoolv1/tests/test_wrapper_codegen.py) | `smartdevtool/wrapper/codegen.py` | Feature 1: Jinja & AST check |
| [`tests/test_deps_scanner.py`](file:///d:/Project/smartdevtoolv1/tests/test_deps_scanner.py) | `smartdevtool/deps/scanner.py` | Feature 2: AST import extraction |
| [`tests/test_deps_mapper.py`](file:///d:/Project/smartdevtoolv1/tests/test_deps_mapper.py) | `smartdevtool/deps/mapper.py` | Feature 2: Module→PyPI name mapping |
| [`tests/test_deps_resolver.py`](file:///d:/Project/smartdevtoolv1/tests/test_deps_resolver.py) | `smartdevtool/deps/resolver.py` | Feature 2: `pip-compile` execution |
| [`tests/test_conflict_agent.py`](file:///d:/Project/smartdevtoolv1/tests/test_conflict_agent.py) | `smartdevtool/deps/conflict_agent.py` | Feature 2: Self-healing conflict loop |
| [`tests/test_docker_gen.py`](file:///d:/Project/smartdevtoolv1/tests/test_docker_gen.py) | `smartdevtool/docker/dockerfile_gen.py` | Feature 3: Dockerfile generation |
| [`tests/test_docker_sync.py`](file:///d:/Project/smartdevtoolv1/tests/test_docker_sync.py) | `smartdevtool/docker/sync_agent.py` | Feature 3: Watchdog sync events |
