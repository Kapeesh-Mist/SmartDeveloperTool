"""Rich console helpers used by every feature's CLI and agentic checkpoints.

Provides a unified visual language across deps, wrapper, and docker commands.
Safely handles Windows cp1252 encoding environments.
"""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

# Configure console for cross-platform robustness, especially Windows legacy consoles
console = Console(safe_box=True)

# Use ASCII-safe glyphs on Windows to avoid UnicodeEncodeError in non-UTF-8 console code pages (e.g. cp1252)
_IS_WINDOWS = sys.platform == "win32"
_STEP_GLYPH = ">" if _IS_WINDOWS else "❯"
_SUCCESS_GLYPH = "[OK]" if _IS_WINDOWS else "✔"
_WARN_GLYPH = "[!]" if _IS_WINDOWS else "▲"
_ERROR_GLYPH = "[X]" if _IS_WINDOWS else "✖"


def header(title: str) -> None:
    """Display a distinct styled header."""
    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]", style="cyan")
    console.print()


def step(message: str) -> None:
    """Display an in-progress or sequential step."""
    console.print(f"[bold blue]{_STEP_GLYPH}[/bold blue] {message}")


def success(message: str) -> None:
    """Display a success outcome."""
    console.print(f"[bold green]{_SUCCESS_GLYPH}[/bold green] {message}")


def warn(message: str) -> None:
    """Display a warning message."""
    console.print(f"[bold yellow]{_WARN_GLYPH}[/bold yellow] {message}")


def error(message: str) -> None:
    """Display an error message."""
    console.print(f"[bold red]{_ERROR_GLYPH}[/bold red] {message}")


def agent_attempt(iteration: int, max_iters: int, action: str) -> None:
    """Display an agent attempt iteration checkpoint."""
    console.print(
        f"[magenta]* Agent Loop [bold][{iteration}/{max_iters}][/bold]:[/magenta] {action}"
    )


def confirm(prompt: str, default: bool = True, auto_yes: bool = False) -> bool:
    """Prompt user for confirmation, or auto-accept if auto_yes is set."""
    if auto_yes:
        console.print(f"[dim]{prompt} [y/N]:[/dim] [bold green]y[/bold green] [dim](auto-yes)[/dim]")
        return True
    return Confirm.ask(prompt, default=default, console=console)


def summary_panel(title: str, content: str | dict[str, Any] | list[Any]) -> None:
    """Render a structured summary panel."""
    if isinstance(content, dict):
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="bold cyan")
        table.add_column("Value")
        for k, v in content.items():
            table.add_row(str(k), str(v))
        console.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="cyan"))
    elif isinstance(content, list):
        text = "\n".join(f"* {item}" for item in content)
        console.print(Panel(text, title=f"[bold]{title}[/bold]", border_style="cyan"))
    else:
        console.print(Panel(str(content), title=f"[bold]{title}[/bold]", border_style="cyan"))
