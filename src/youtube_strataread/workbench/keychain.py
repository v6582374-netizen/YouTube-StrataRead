"""Profile-owned OAuth credentials in the operating system's credential store.

The complete record is written atomically. The record is cached only in this
process, so navigation never reopens the credential store. A headless server
has no credential store; it opts in to a file readable only by its service
account via ``EDISON_CREDENTIAL_FILE``, and nothing falls back to it silently.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from youtube_strataread.workbench.vault import VaultError


class ServiceAccountFile:
    """Keyring-shaped store in one owner-only JSON file for a headless service account."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _records(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get_password(self, service: str, account: str) -> str | None:
        return self._records().get(f"{service}/{account}")

    def set_password(self, service: str, account: str, value: str) -> None:
        records = {**self._records(), f"{service}/{account}": value}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staging = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(records, handle)
        os.replace(staging, self.path)


class NativeKeychainVault:
    service = "netizen.v6582374.edison.youtube"

    def __init__(self, *, namespace: str, backend: Any = None) -> None:
        self.account = hashlib.sha256(namespace.encode()).hexdigest()
        self._backend = backend
        self._values: dict[str, str] | None = None
        self._lock = threading.RLock()

    def _store(self):
        if self._backend is None:
            # Select a native backend explicitly. A file store is used only when opted in.
            if os.environ.get("EDISON_CREDENTIAL_FILE"):
                self._backend = ServiceAccountFile(Path(os.environ["EDISON_CREDENTIAL_FILE"]))
            elif sys.platform == "darwin":
                from keyring.backends.macOS import Keyring

                self._backend = Keyring()
            elif sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring

                self._backend = WinVaultKeyring()
            else:
                from keyring.backends.SecretService import Keyring

                self._backend = Keyring()
        return self._backend

    def _read(self) -> dict[str, str]:
        if self._values is None:
            try:
                value = self._store().get_password(self.service, self.account)
                values = json.loads(value) if value else {}
                if not isinstance(values, dict) or any(
                    not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()
                ):
                    raise ValueError("invalid credential record")
                self._values = values
            except Exception as error:
                raise VaultError(
                    "System credential store is unavailable; unlock it and retry"
                ) from error
        return self._values

    def keys(self) -> set[str]:
        with self._lock:
            return {key for key, value in self._read().items() if value}

    def load(self, key: str) -> str | None:
        with self._lock:
            return self._read().get(key) or None

    def save(self, key: str, value: str) -> None:
        self.save_many({key: value})

    def save_many(self, values: dict[str, str]) -> None:
        with self._lock:
            updated = {**self._read(), **values}
            updated = {key: value for key, value in updated.items() if value}
            try:
                # Short-lived bearer material exists only in this process. On a
                # cold start, obtain a fresh access token using the Keychain refresh token.
                durable = {
                    key: value
                    for key, value in updated.items()
                    if key
                    not in {
                        "YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN",
                        "YOUTUBE_WORKBENCH_OAUTH_EXPIRES_AT",
                    }
                }
                self._store().set_password(self.service, self.account, json.dumps(durable))
            except Exception as error:
                raise VaultError(
                    "System credential store could not save the YouTube connection"
                ) from error
            self._values = updated
