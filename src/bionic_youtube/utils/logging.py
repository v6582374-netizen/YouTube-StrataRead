"""Thin wrapper around rich console for consistent output."""
from __future__ import annotations

import logging
import sys
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

_stderr_console = Console(stderr=True)
_stdout_console = Console()

_logger = logging.getLogger("bionic_youtube")
_configured = False


def configure(verbose: bool = False, no_color: bool = False) -> None:
    """Configure root logger. Safe to call multiple times."""
    global _configured
    if _configured:
        return
    _configured = True

    if no_color:
        _stdout_console.no_color = True
        _stderr_console.no_color = True

    level = logging.DEBUG if verbose else logging.INFO
    handler = RichHandler(
        console=_stderr_console,
        rich_tracebacks=True,
        show_path=False,
        show_time=False,
        markup=True,
    )
    _logger.setLevel(level)
    _logger.handlers.clear()
    _logger.addHandler(handler)
    _logger.propagate = False


def get_logger() -> logging.Logger:
    return _logger


def stdout() -> Console:
    return _stdout_console


def stderr() -> Console:
    return _stderr_console


def die(msg: str, code: int = 1) -> Any:
    """Print an error to stderr and exit."""
    _stderr_console.print(f"[bold red]error:[/] {msg}")
    sys.exit(code)
