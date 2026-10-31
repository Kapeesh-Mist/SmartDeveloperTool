"""SmartDevTool Dependency Resolver feature package."""

from smartdevtool.deps.scanner import ImportScanner
from smartdevtool.deps.mapper import map_import_to_distribution, map_imports
from smartdevtool.deps.resolver import (
    DependencyResolver,
    CompileResult,
    is_resolution_conflict,
)
from smartdevtool.deps.conflict_agent import ConflictAgent, ResolutionResult
from smartdevtool.deps.installer import DependencyInstaller

__all__ = [
    "ImportScanner",
    "map_import_to_distribution",
    "map_imports",
    "DependencyResolver",
    "CompileResult",
    "is_resolution_conflict",
    "ConflictAgent",
    "ResolutionResult",
    "DependencyInstaller",
]
