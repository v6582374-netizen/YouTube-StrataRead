from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from youtube_strataread.workbench.vault import AutomicVault, VaultError


def test_vault_hides_missing_cli_as_a_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(VaultError, match="Automic Vault is unavailable"):
        AutomicVault(executable=Path("/missing/av")).save("OAUTH_CLIENT", "value")


def test_vault_hides_timeout_as_a_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def timed_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="av", timeout=30)

    monkeypatch.setattr(subprocess, "run", timed_out)

    with pytest.raises(VaultError, match="Automic Vault is unavailable"):
        AutomicVault(executable=Path("/missing/av")).save("OAUTH_CLIENT", "value")


def test_vault_load_returns_no_value_when_injection_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        ),
    )

    assert AutomicVault(executable=Path("/fake/av")).load("OAUTH_CLIENT") is None


def test_vault_save_uses_noninteractive_stdin_without_altering_secret(monkeypatch):
    def run(args, **kwargs):
        assert args[1:3] == ["save", "--stdin"]
        assert kwargs["input"] == "fixture-value"
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    AutomicVault(executable=Path("/fake/av")).save("OAUTH_CLIENT", "fixture-value")
