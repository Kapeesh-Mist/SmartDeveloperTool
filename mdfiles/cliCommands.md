
# CLI COMMANDS AND FLAGS

### 1. `smartdevtool version`
Displays the installed version of `smartdevtool`.
* **Usage**:
  ```bash
  smartdevtool version
  ```
* **Arguments / Flags**: None (prints `smartdevtool v0.1.0`).

---

### 2. `smartdevtool wrapper`
Generates a typed Python SDK client from one or more input formats (cURL, Postman, HAR, OpenAPI) with Jinja2 templating, AST validation, and self-correcting HTTP validation.

* **Usage**:
  ```bash
  smartdevtool wrapper [OPTIONS]
  ```
* **Input Options** *(at least one required)*:
  * `--curl <text>`: Raw cURL command string to convert into an SDK.
  * `--postman <path>`: Path to a Postman Collection v2.x `.json` file.
  * `--har <path>`: Path to a browser network capture `.har` file.
  * `--doc <path_or_url>`: Path or URL to an OpenAPI/Swagger spec or markdown prose doc.
* **Configuration Flags**:
  * `--name <text>`: Custom class name for the generated client (defaults to spec title or `ApiClient`; auto-appends `Client`).
  * `--output-dir <path>`: Directory where the generated SDK is saved (default: `.`).
  * `--base-url <url>`: Override the API base URL.
  * `--no-llm`: Bypass LLM structurer and validation suggestions; use only deterministic parsers.
  * `--no-validate`: Skip automated live `GET` endpoint self-correction.
  * `--max-iters <int>`: Max retry attempts for validation agent self-correction (default: `6` from config).
  * `-y`, `--yes`: Automatically confirm all interactive prompts.
* **Example**:
  ```bash
  smartdevtool wrapper --curl "curl -H 'Authorization: Bearer test' https://api.github.com/user" --name GitHub --output-dir . --no-llm -y
  ```

---

# 📦 Command Group: `smartdevtool deps`

Manages dependency scanning, conflict-free resolution via `pip-compile`, and installation.

### 1. `smartdevtool deps scan [PATH]`
Performs a read-only AST parse of all Python files to extract 3rd-party imports and maps them to canonical PyPI distribution names.
* **Usage**:
  ```bash
  smartdevtool deps scan [PATH]
  ```
* **Arguments**:
  * `PATH`: Project root directory to scan (optional, default: `.`).
* **Example**:
  ```bash
  smartdevtool deps scan .
  ```

### 2. `smartdevtool deps install [PATH]`
Scans the project (or reads existing `requirements.in`), resolves conflicts using `ConflictAgent` (backtracking unpinning + `pip-compile`), updates `.smartdevtool/manifest.json`, and installs packages.
* **Usage**:
  ```bash
  smartdevtool deps install [PATH] [OPTIONS]
  ```
* **Arguments**:
  * `PATH`: Project directory to resolve and install (optional, default: `.`).
* **Options & Flags**:
  * `-o`, `--output <path>`: Output lockfile filename (default: `requirements.txt`).
  * `--dry-run`: Resolves and writes lockfile without actually installing packages into the environment.
  * `--venv`: Installs packages into an isolated `.smartdevtool/venv` instead of the active environment.
  * `--no-llm`: Bypasses LLM conflict suggestions; relies purely on deterministic heuristic unpinning.
  * `--max-iters <int>`: Maximum retry attempts for conflict resolution (default: `8` from config).
  * `-y`, `--yes`: Automatically confirms prompts.
* **Example**:
  ```bash
  smartdevtool deps install . --dry-run --output requirements.lock --no-llm -y
  ```

---

# 🐳 Command Group: `smartdevtool docker`

Generates layer-cached Dockerfiles and monitors for environment drift.

### 1. `smartdevtool docker build [PATH]`
Inspects dependencies and manifest state, generates an optimized `Dockerfile` (layering dependencies first), and builds the Docker image.
* **Usage**:
  ```bash
  smartdevtool docker build [PATH] [OPTIONS]
  ```
* **Arguments**:
  * `PATH`: Project root directory to build (optional, default: `.`).
* **Options & Flags**:
  * `-t`, `--tag <text>`: Docker image tag (default: `smartdevtool:latest`).
  * `--no-llm`: Bypass LLM base image recommendation; use deterministic Python base heuristics.
  * `-y`, `--yes`: Automatically confirm build prompts.
* **Example**:
  ```bash
  smartdevtool docker build . --tag myapp:1.0.0 --no-llm -y
  ```

### 2. `smartdevtool docker sync [PATH]`
Calculates SHA-256 fingerprints of source files to detect drift from the last recorded build in `.smartdevtool/manifest.json`.
* **Usage**:
  ```bash
  smartdevtool docker sync [PATH] [OPTIONS]
  ```
* **Arguments**:
  * `PATH`: Project root directory to sync (optional, default: `.`).
* **Options & Flags**:
  * `-w`, `--watch`: Continuously runs in the background using `watchdog` to monitor file saves. *(If omitted, it performs a single one-time drift check `sync_once()`)*.
  * `-t`, `--tag <text>`: Docker image tag to rebuild (default: `smartdevtool:latest`).
  * `--no-llm`: Bypass LLM natural-language drift summary.
  * `-y`, `--yes`: Automatically confirm container rebuilds without prompting.
* **Example**:
  ```bash
  smartdevtool docker sync . --watch --tag myapp:1.0.0 --yes
  ```

---

# 📑 Summary Table of All CLI Commands

| Full Command Path | Key Purpose | Notable Flags |
| :--- | :--- | :--- |
| `smartdevtool version` | Check CLI version | — |
| `smartdevtool wrapper` | Generate SDK wrapper | `--curl`, `--postman`, `--har`, `--doc`, `--name`, `--output-dir`, `--no-llm`, `--no-validate`, `-y` |
| `smartdevtool deps scan [PATH]` | Scan AST imports & PyPI map | `[PATH]` |
| `smartdevtool deps install [PATH]` | Resolve & install dependencies | `--dry-run`, `--venv`, `-o / --output`, `--no-llm`, `--max-iters`, `-y` |
| `smartdevtool docker build [PATH]` | Generate `Dockerfile` & build | `-t / --tag`, `--no-llm`, `-y` |
| `smartdevtool docker sync [PATH]` | Drift detection & live watcher | `-w / --watch`, `-t / --tag`, `--no-llm`, `-y` |




##################################################### START-UP_Guide ###################################################

