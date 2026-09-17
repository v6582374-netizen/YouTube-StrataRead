"""The Automic Vault boundary for workbench OAuth material."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol


class VaultError(RuntimeError):
    """Raised without including a secret value when the local vault rejects an operation."""


class SecretVault(Protocol):
    """Persists and retrieves secrets without placing them in workspace assets."""

    def save(self, key: str, value: str) -> None: ...

    def load(self, key: str) -> str | None: ...


class AutomicVault:
    """Uses the local Automic Vault CLI as the only production secret store."""

    def __init__(self, executable: Path | None = None, *, timeout: int = 30) -> None:
        self.executable = executable
        self.timeout = timeout

    def save(self, key: str, value: str) -> None:
        self._run(["save", key], input=f"{value}\n")

    def load(self, key: str) -> str | None:
        result = self._run(
            ["inject", f"+{key}", "--", "/usr/bin/printenv", key], allow_failure=True
        )
        if result is None:
            return None
        value = result.stdout.rstrip("\n")
        return value or None

    def _executable(self) -> Path:
        return self.executable or _default_executable()

    def _run(
        self,
        arguments: list[str],
        *,
        input: str | None = None,
        allow_failure: bool = False,
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            result = subprocess.run(
                [str(self._executable()), *arguments],
                input=input,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise VaultError("Automic Vault is unavailable") from error
        if result.returncode != 0:
            if allow_failure:
                return None
            raise VaultError("Automic Vault could not save the requested credential")
        return result


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
