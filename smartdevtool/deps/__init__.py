"""SmartDevTool Dependency Resolver feature package."""

from smartdevtool.deps.conflict_agent import ConflictAgent, ResolutionResult
from smartdevtool.deps.installer import DependencyInstaller
from smartdevtool.deps.mapper import map_import_to_distribution, map_imports
from smartdevtool.deps.resolver import (
    CompileResult,
    DependencyResolver,
    is_resolution_conflict,
)
from smartdevtool.deps.scanner import ImportScanner

__all__ = [
    "CompileResult",
    "ConflictAgent",
    "DependencyInstaller",
    "DependencyResolver",
    "ImportScanner",
    "ResolutionResult",
    "is_resolution_conflict",
    "map_import_to_distribution",
    "map_imports",
]
