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


def test_vault_listing_failure_is_not_missing_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        ),
    )

    with pytest.raises(VaultError):
        AutomicVault(executable=Path("/fake/av")).load("OAUTH_CLIENT")


def test_vault_save_uses_noninteractive_stdin_without_altering_secret(monkeypatch):
    def run(args, **kwargs):
        assert args[1:3] == ["save", "--stdin"]
        assert kwargs["input"] == "fixture-value"
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    AutomicVault(executable=Path("/fake/av")).save("OAUTH_CLIENT", "fixture-value")


def test_profiles_never_share_oauth_keys(monkeypatch):
    saved = {}

    def run(self, arguments, *, input=None, allow_failure=False):
        from types import SimpleNamespace

        if arguments[0] == "list":
            return SimpleNamespace(stdout="\n".join(saved))
        if arguments[0] == "save":
            saved[arguments[-1]] = input
            return SimpleNamespace(stdout="")
        return SimpleNamespace(stdout=saved.get(arguments[-1], ""))

    monkeypatch.setattr(AutomicVault, "_run", run)
    legacy = AutomicVault()
    development = AutomicVault(namespace="/profiles/edison-dev/youtube")
    release = AutomicVault(namespace="/profiles/edison/youtube")
    legacy.save("ACCESS_TOKEN", "old-account")
    development.save("ACCESS_TOKEN", "developer-account")
    assert release.load("ACCESS_TOKEN") is None
    release.save("ACCESS_TOKEN", "release-account")
    assert release.load("ACCESS_TOKEN") == "release-account"
    assert legacy.load("ACCESS_TOKEN") == "old-account"
    assert development.load("ACCESS_TOKEN") == "developer-account"
    assert (
        AutomicVault(namespace="/profiles/edison/youtube").load("ACCESS_TOKEN") == "release-account"
    )


def test_existing_client_is_reused_as_a_pair_without_inheriting_account_tokens(monkeypatch):
    vault = AutomicVault(namespace="/release/youtube")
    client_id = "YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID"
    client_secret = "YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET"
    token = "YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN"
    values = {client_id: "shared-id", client_secret: "shared-secret", token: "legacy-account"}
    injected = []

    def run(args, **kwargs):
        if args[1] == "list":
            return subprocess.CompletedProcess(args, 0, "\n".join(values), "")
        injected.append(args[-1])
        return subprocess.CompletedProcess(args, 0, values[args[-1]], "")

    monkeypatch.setattr(subprocess, "run", run)
    assert vault.keys() == {client_id, client_secret}
    assert injected == []
    assert vault.load(client_id) == "shared-id"
    assert vault.load(client_secret) == "shared-secret"
    assert vault.load(token) is None
    values[vault.prefix + client_id] = "custom-id"
    assert vault.load(client_secret) is None  # Never mix half of two OAuth clients.
    values[vault.prefix + client_secret] = "custom-secret"
    assert vault.load(client_id) == "custom-id"
    assert vault.load(client_secret) == "custom-secret"
    assert token not in injected


def test_present_but_denied_secret_is_not_reported_missing(monkeypatch):
    def run(args, **kwargs):
        return subprocess.CompletedProcess(
            args, 0 if args[1] == "list" else 1, "CLIENT" if args[1] == "list" else "", ""
        )

    monkeypatch.setattr(subprocess, "run", run)
    vault = AutomicVault()
    assert vault.load("ABSENT") is None
    with pytest.raises(VaultError):
        vault.load("CLIENT")


def test_batch_migration_reads_every_field_with_real_macos_printenv(monkeypatch):
    import os

    vault = AutomicVault(namespace="/release")
    keys = [
        "YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID",
        "YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET",
        "YOUTUBE_WORKBENCH_OAUTH_REFRESH_TOKEN",
    ]
    names = [keys[0], keys[1], vault.prefix + keys[2]]
    values = ["fixture-client", "fixture-secret", "fixture-refresh"]
    original_run = subprocess.run
    injections = []

    def run(args, **kwargs):
        if args[1] == "list":
            return subprocess.CompletedProcess(args, 0, "\n".join(names), "")
        injections.append(args)
        command = args[args.index("--") + 1 :]
        return original_run(
            command, env={**os.environ, **dict(zip(names, values, strict=True))}, **kwargs
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert vault.export_credentials(keys) == dict(zip(keys, values, strict=True))
    assert len(injections) == 1
    assert all(value not in injections[0] for value in values)
