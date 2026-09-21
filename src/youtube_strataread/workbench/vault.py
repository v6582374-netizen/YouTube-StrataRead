"""The Automic Vault boundary for workbench OAuth material."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol


class VaultError(RuntimeError):
    """Raised without including a secret value when the local vault rejects an operation."""


class SecretVault(Protocol):
    """Persists and retrieves secrets without placing them in workspace assets."""

    def keys(self) -> set[str]: ...

    def save_many(self, values: dict[str, str]) -> None: ...

    def save(self, key: str, value: str) -> None: ...

    def load(self, key: str) -> str | None: ...


class AutomicVault:
    """Explicit migration adapter for legacy Automic Vault credentials."""

    def __init__(
        self, executable: Path | None = None, *, timeout: int = 30, namespace: str | None = None
    ) -> None:
        self.prefix = (
            "EDISON_" + hashlib.sha256(namespace.encode()).hexdigest()[:16] + "_"
            if namespace
            else ""
        )
        self.executable = executable
        self.timeout = timeout

    def save(self, key: str, value: str) -> None:
        self._run(["save", "--stdin", self.prefix + key], input=value)

    def save_many(self, values: dict[str, str]) -> None:
        for key, value in values.items():
            self.save(key, value)

    def export_credentials(self, keys: list[str]) -> dict[str, str]:
        """Explicit one-time migration; one Vault approval, no local plaintext file."""
        mapping = self._key_map()
        selected = [key for key in keys if key in mapping]
        if not selected:
            return {}
        actual = [mapping[key] for key in selected]
        # BSD printenv on macOS accepts only one name (extra names are ignored).
        # Keep values out of argv and collect each field inside one approved process.
        result = self._run(
            [
                "inject",
                *("+" + key for key in actual),
                "--",
                "/bin/sh",
                "-c",
                'for key do /usr/bin/printenv "$key" || exit; done',
                "edison-credential-migration",
                *actual,
            ]
        )
        values = result.stdout.splitlines()
        if len(values) != len(selected):
            raise VaultError("Existing OAuth credentials could not be migrated")
        return dict(zip(selected, values, strict=True))

    def _key_map(self) -> dict[str, str]:
        # Listing names does not reveal or request access to secret values.
        result = self._run(["list"])
        names = set(result.stdout.splitlines())
        scoped = {name[len(self.prefix) :]: name for name in names if name.startswith(self.prefix)}
        clients = {"YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID", "YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET"}
        # A profile-specific client takes precedence as a pair. Never combine clients
        # or inherit another profile's account tokens.
        if self.prefix and not clients.intersection(scoped):
            scoped.update({key: key for key in clients if key in names})
        return scoped

    def keys(self) -> set[str]:
        return set(self._key_map())

    def load(self, key: str) -> str | None:
        actual = self._key_map().get(key)
        if actual is None:
            return None
        result = self._run(["inject", f"+{actual}", "--", "/usr/bin/printenv", actual])
        return result.stdout.rstrip("\n") or None

    def _executable(self) -> Path:
        return self.executable or _default_executable()

    def _run(
        self,
        arguments: list[str],
        *,
        input: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
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
            raise VaultError("Automic Vault could not complete the requested operation")
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
