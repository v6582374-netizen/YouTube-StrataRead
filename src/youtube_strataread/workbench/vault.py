"""The Automic Vault boundary for workbench OAuth material."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Protocol
from pathlib import Path


class VaultError(RuntimeError):
    """Raised without including a secret value when the local vault rejects an operation."""


class SecretVault(Protocol):
    """Persists and retrieves secrets without placing them in workspace assets."""

    def save(self, key: str, value: str) -> None: ...

    def load(self, key: str) -> str | None: ...


class AutomicVault:
    """Uses the local Automic Vault CLI as the only production secret store."""

    def __init__(self, executable: Path | None = None) -> None:
        self.executable = executable or _default_executable()

    def save(self, key: str, value: str) -> None:
        result = subprocess.run(
            [str(self.executable), "save", key],
            input=f"{value}\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise VaultError("Automic Vault could not save the requested credential")

    def load(self, key: str) -> str | None:
        result = subprocess.run(
            [str(self.executable), "inject", f"+{key}", "--", "/usr/bin/printenv", key],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.rstrip("\n")
        return value or None


def _default_executable() -> Path:
    configured = os.environ.get("YOUTUBE_WORKBENCH_AUTOMIC_VAULT")
    if configured:
        return Path(configured)
    installed = shutil.which("av")
    if installed:
        return Path(installed)
    bundled = Path("/Applications/Automic Vault.app/Contents/MacOS/av")
    if bundled.exists():
        return bundled
    raise VaultError("Automic Vault CLI is not installed")
