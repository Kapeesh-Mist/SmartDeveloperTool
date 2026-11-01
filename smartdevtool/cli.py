"""SmartDevTool unified CLI entrypoint."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from smartdevtool import ui
from smartdevtool.config import Config
from smartdevtool.deps import (
    ConflictAgent,
    DependencyInstaller,
    DependencyResolver,
    ImportScanner,
    map_imports,
)
from smartdevtool.docker import (
    DockerBuilder,
    DockerfileGenerator,
    SyncAgent,
    docker_available,
)
from smartdevtool.llm.client import LLMClient
from smartdevtool.manifest import ManifestManager
from smartdevtool.wrapper import (
    CurlParser,
    DocParser,
    EndpointSpec,
    HarParser,
    LLMStructurer,
    Normalizer,
    PostmanParser,
    ValidationAgent,
    WrapperGenerator,
)

app = typer.Typer(
    name="smartdevtool",
    help="SmartDevTool: CLI + Python library that automates API integration and environment reproducibility.",
    no_args_is_help=True,
)

deps_app = typer.Typer(
    name="deps",
    help="Feature 2: Scan and resolve conflict-free Python dependencies using real pip-compile.",
    no_args_is_help=True,
)
app.add_typer(deps_app, name="deps")

docker_app = typer.Typer(
    name="docker",
    help="Feature 3: Generate Dockerfiles and sync build state on environment drift.",
    no_args_is_help=True,
)
app.add_typer(docker_app, name="docker")


# =====================================================================
# ROOT COMMANDS
# =====================================================================

@app.command(name="version")
def version() -> None:
    """Show smartdevtool package version."""
    ui.console.print("smartdevtool v0.1.0")


# =====================================================================
# FEATURE 2: DEPENDENCY RESOLVER COMMANDS
# =====================================================================

@deps_app.command(name="scan")
def deps_scan(
    path: Path = typer.Argument(Path("."), help="Project directory to scan for imports"),
) -> None:
    """Read-only scan of third-party imports via Python's AST."""
    ui.header(f"Scanning Python imports in: {path.resolve()}")
    scanner = ImportScanner(project_root=path)
    imports = sorted(scanner.scan())

    if not imports:
        ui.warn("No third-party imports detected.")
        return

    dist_map = map_imports(imports)
    ui.summary_panel(
        f"Detected Imports ({len(imports)})",
        {imp: dist_map[imp] for imp in imports},
    )
    ui.success(f"Successfully identified {len(imports)} third-party dependencies.")


@deps_app.command(name="install")
def deps_install(
    path: Path = typer.Argument(Path("."), help="Project directory to resolve and install"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Resolve without installing packages"),
    use_venv: bool = typer.Option(False, "--venv", help="Install into isolated .smartdevtool/venv"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Bypass LLM and use deterministic heuristic fallback"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto-confirm prompts"),
    max_iters: int | None = typer.Option(None, "--max-iters", help="Maximum agentic retry attempts"),
    output: Path = typer.Option(Path("requirements.txt"), "-o", "--output", help="Output lockfile path"),
) -> None:
    """Resolve project imports into a pinned lockfile and install them."""
    cfg = Config.load(max_iters_deps=max_iters)
    actual_max_iters = max_iters if max_iters is not None else cfg.max_iters_deps

    ui.header("SmartDevTool Dependency Resolver")
    ui.step(f"Scanning imports in {path.resolve()}...")

    # Step 1: Scan
    scanner = ImportScanner(project_root=path)
    imports = sorted(scanner.scan())

    # Check for existing requirements.in or requirements.txt if scanner found nothing or to supplement
    reqs_in_file = path / "requirements.in"
    initial_reqs: list[str] = []

    if reqs_in_file.exists():
        ui.step(f"Found existing requirements file: {reqs_in_file.name}")
        with open(reqs_in_file, encoding="utf-8") as f:
            initial_reqs = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not initial_reqs:
        dist_map = map_imports(imports)
        initial_reqs = sorted(set(dist_map.values()))

    if not initial_reqs:
        ui.warn("No dependencies detected to resolve.")
        return

    ui.summary_panel("Initial Requirements", initial_reqs)

    if not ui.confirm("Proceed with backtracking dependency resolution?", default=True, auto_yes=yes):
        ui.warn("Operation aborted by user.")
        return

    # Step 2: Resolve with ConflictAgent
    llm_client = None if no_llm else LLMClient(cfg)
    resolver = DependencyResolver()
    agent = ConflictAgent(
        resolver=resolver,
        llm_client=llm_client,
        max_iters=actual_max_iters,
    )

    out_file = path / output
    result = agent.resolve(initial_reqs, output_file=out_file)

    if not result.success:
        ui.error(f"Dependency resolution failed: {result.error}")
        raise typer.Exit(code=1)

    # Step 3: Record to manifest
    dist_map = map_imports(imports)
    mgr = ManifestManager(project_root=path)
    mgr.record_dependencies(
        imports=imports,
        distribution_map=dist_map,
        pinned_dependencies=result.final_requirements,
        lockfile_path=str(out_file),
    )
    ui.success(f"Manifest updated with {len(result.final_requirements)} resolved dependencies.")

    # Step 4: Install
    venv_dir = (path / ".smartdevtool" / "venv") if use_venv else None
    installer = DependencyInstaller()
    ok, msg = installer.install(out_file, venv_dir=venv_dir, dry_run=dry_run)

    if ok:
        ui.success("Dependencies successfully resolved and installed!")
    else:
        ui.error(f"Installation error:\n{msg}")
        raise typer.Exit(code=1)


# =====================================================================
# FEATURE 1: WRAPPER GENERATION COMMANDS
# =====================================================================

@app.command(name="wrapper")
def wrapper_generate(
    curl: str | None = typer.Option(None, "--curl", help="Curl command string to convert into an SDK"),
    postman: Path | None = typer.Option(None, "--postman", help="Path to Postman Collection v2.x JSON file"),
    har: Path | None = typer.Option(None, "--har", help="Path to browser network capture .har file"),
    doc: str | None = typer.Option(None, "--doc", help="Path or URL to OpenAPI spec or prose documentation"),
    name: str | None = typer.Option(None, "--name", help="Custom name for the generated SDK client class"),
    output_dir: Path = typer.Option(Path("."), "--output-dir", help="Directory where generated SDK is saved"),
    base_url: str | None = typer.Option(None, "--base-url", help="Override base URL for API calls"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Bypass LLM structurer and validation suggestions"),
    no_validate: bool = typer.Option(False, "--no-validate", help="Skip automated GET endpoint validation"),
    max_iters: int | None = typer.Option(None, "--max-iters", help="Max validation retry iterations"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto-confirm all prompts"),
) -> None:
    """Feature 1: Generate a validated Python SDK wrapper class from curl/HAR/Postman/OpenAPI."""
    cfg = Config.load(max_iters_wrapper=max_iters)
    actual_max_iters = max_iters if max_iters is not None else cfg.max_iters_wrapper

    ui.header("SmartDevTool API Wrapper Generator")

    specs: list[EndpointSpec] = []

    # 1. Parse deterministic inputs
    if curl:
        ui.step("Parsing curl command...")
        specs.append(CurlParser(curl).parse())

    if postman:
        ui.step(f"Parsing Postman collection from {postman}...")
        specs.append(PostmanParser(postman).parse())

    if har:
        ui.step(f"Parsing HAR network capture from {har}...")
        specs.append(HarParser(har).parse())

    if doc:
        ui.step(f"Parsing API documentation from {doc}...")
        specs.append(DocParser(doc).parse())

    if not specs:
        ui.warn("No input provided. Specify at least one of --curl, --postman, --har, or --doc.")
        raise typer.Exit(code=1)

    # 2. Normalize and merge
    merged_spec = Normalizer.merge(specs)

    # 3. LLM escalation if no endpoints found
    if not merged_spec.endpoints and not no_llm:
        ui.step("Deterministic parsers found no endpoints. Escalating to LLM Structurer...")
        llm_client = LLMClient(cfg)
        raw_context = curl or doc or ""
        if raw_context:
            structurer = LLMStructurer(llm_client)
            llm_spec = structurer.structure(raw_context)
            if llm_spec and llm_spec.endpoints:
                merged_spec = llm_spec

    if not merged_spec.endpoints:
        ui.error("No valid API endpoints could be extracted from the provided input.")
        raise typer.Exit(code=1)

    # Apply base_url override
    if base_url:
        merged_spec.base_url = base_url

    # Apply class name override
    class_name = name or merged_spec.title or "ApiClient"
    if not class_name.endswith("Client"):
        class_name = f"{class_name}Client"
    merged_spec.title = class_name

    ui.summary_panel(
        f"API Specification: {class_name}",
        {
            "Base URL": merged_spec.base_url or "(relative)",
            "Auth Type": f"{merged_spec.auth.type} ({merged_spec.auth.header_name})",
            "Endpoints Detected": len(merged_spec.endpoints),
            "Source Format": merged_spec.source_format,
        },
    )

    if not ui.confirm("Proceed with Python SDK wrapper code generation?", default=True, auto_yes=yes):
        ui.warn("Operation aborted by user.")
        return

    # 4. Generate code via Jinja2
    generator = WrapperGenerator(merged_spec, class_name=class_name)
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", class_name).lower()
    output_file = output_dir / f"{clean_name}_sdk.py"
    generator.write(output_file)
    ui.success(f"Generated Python SDK client saved to: {output_file.resolve()}")

    # 5. Agentic Validation Loop
    if not no_validate:
        ui.step("Starting agentic validation loop...")
        llm_client = None if no_llm else LLMClient(cfg)
        agent = ValidationAgent(
            wrapper_file=output_file,
            spec=merged_spec,
            llm_client=llm_client,
            max_iters=actual_max_iters,
        )
        val_result = agent.validate()
        if not val_result.success:
            ui.warn(f"Validation finished with warning: {val_result.error}")

    # 6. Record in manifest
    mgr = ManifestManager(project_root=output_dir)
    mgr.record_wrapper(
        name=class_name,
        source_type=merged_spec.source_format,
        file_path=str(output_file),
        base_url=merged_spec.base_url,
        endpoints=[f"{ep.method} {ep.path}" for ep in merged_spec.endpoints],
        auth_type=merged_spec.auth.type,
    )
    ui.success("Manifest updated at .smartdevtool/manifest.json with wrapper metadata.")


# =====================================================================
# FEATURE 3: DOCKER SYNC COMMANDS
# =====================================================================

@docker_app.command(name="build")
def docker_build(
    path: Path = typer.Argument(Path("."), help="Project root directory to build"),
    tag: str = typer.Option("smartdevtool:latest", "--tag", "-t", help="Docker image tag"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Bypass LLM base image suggestion"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto-confirm prompts"),
) -> None:
    """Generate a tailored Dockerfile and build the project image."""
    ui.header(f"SmartDevTool Docker Build [{tag}]")
    cfg = Config.load()
    llm_client = None if no_llm else LLMClient(cfg)

    # 1. Check Docker availability
    if not docker_available():
        ui.warn("Docker binary is not installed or the Docker daemon is not running.")
        ui.step("Generating Dockerfile locally without executing docker build...")

    # 2. Load manifest for dependencies
    mgr = ManifestManager(project_root=path)
    manifest = mgr.load()
    deps = manifest.dependencies.pinned_dependencies or []

    # Gather environment variable names from manifest wrappers
    env_vars: list[str] = []
    for w in manifest.wrappers:
        # Avoid baking any secrets; names only
        if w.auth_type in ("api_key", "jwt"):
            env_vars.append("API_KEY")

    # 3. Generate Dockerfile
    generator = DockerfileGenerator(llm_client=llm_client)
    df_path = path / "Dockerfile"

    ui.step("Generating optimized layer-cached Dockerfile...")
    generator.write(
        output_path=df_path,
        dependencies=deps,
        env_vars=env_vars,
    )
    ui.success(f"Dockerfile saved to: {df_path.resolve()}")

    # If docker is not available, stop here cleanly
    if not docker_available():
        ui.warn("Skipping image build step because Docker is unavailable.")
        return

    if not ui.confirm(f"Proceed with building Docker image '{tag}'?", default=True, auto_yes=yes):
        ui.warn("Build cancelled by user.")
        return

    # 4. Build image
    ui.step(f"Building Docker image: {tag}...")
    builder = DockerBuilder()
    success, output = builder.build(tag=tag, context_dir=path, dockerfile=df_path)

    if success:
        detector = SyncAgent(project_root=path).change_detector
        h, _ = detector.compute_fingerprint()
        mgr.record_docker(
            base_image=None,
            dockerfile_path="Dockerfile",
            image_tag=tag,
            last_build_hash=h,
        )
        ui.success(f"Docker image '{tag}' built successfully and recorded in manifest!")
    else:
        ui.error(f"Docker build failed:\n{output[:500]}")
        raise typer.Exit(code=1)


@docker_app.command(name="sync")
def docker_sync(
    path: Path = typer.Argument(Path("."), help="Project root directory to sync"),
    tag: str = typer.Option("smartdevtool:latest", "--tag", "-t", help="Docker image tag"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Continuously watch filesystem for changes"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Bypass LLM explanations"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto-confirm rebuild prompts"),
) -> None:
    """Feature 3: Sync Docker image with codebase changes, rebuilding only on detected drift."""
    cfg = Config.load()
    llm_client = None if no_llm else LLMClient(cfg)

    agent = SyncAgent(
        project_root=path,
        image_tag=tag,
        llm_client=llm_client,
        auto_yes=yes,
    )

    if watch:
        agent.watch()
    else:
        agent.sync_once()


if __name__ == "__main__":
    app()
