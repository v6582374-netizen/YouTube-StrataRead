"""Line-oriented capability sidecar for the local desktop workbench."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from youtube_strataread.workbench.connection import (
    ConnectionError,
    ConnectionService,
    GoogleOAuthGateway,
)
from youtube_strataread.workbench.vault import AutomicVault, SecretVault
from youtube_strataread.workbench.workspace import LocalWorkspace, workspace_root


def _silence_broken_stdout() -> None:
    null_output = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null_output, sys.stdout.fileno())
    finally:
        os.close(null_output)


def _response(
    request_id: object, *, result: dict[str, object] | None = None, error: str | None = None
) -> dict[str, object]:
    if error is not None:
        return {"id": request_id, "ok": False, "error": error}
    return {"id": request_id, "ok": True, "result": result}


@dataclass
class _TestVault:
    values: dict[str, str] = field(default_factory=dict)

    def save(self, key: str, value: str) -> None:
        self.values[key] = value

    def load(self, key: str) -> str | None:
        return self.values.get(key)


def _vault() -> SecretVault:
    if os.environ.get("YOUTUBE_WORKBENCH_TEST_VAULT") == "1" and not getattr(sys, "frozen", False):
        return _TestVault()
    return AutomicVault()


def handle_request(
    request: Mapping[str, Any],
    workspace: LocalWorkspace,
    connection: ConnectionService,
) -> dict[str, object]:
    request_id = request.get("id")
    capability = request.get("capability")
    arguments = request.get("arguments", {})
    if not isinstance(arguments, dict):
        return _response(request_id, error="arguments must be an object")
    try:
        if capability == "library.snapshot":
            return _response(request_id, result=workspace.snapshot().as_result())
        if capability == "connection.status":
            return _response(request_id, result=connection.status().as_result())
        if capability == "collection.subscription_sources":
            return _response(request_id, result={"sources": connection.subscription_sources()})
        if capability == "connection.configure":
            return _response(
                request_id,
                result=connection.configure(
                    client_id=str(arguments.get("client_id") or ""),
                    client_secret=str(arguments.get("client_secret") or ""),
                ).as_result(),
            )
        if capability == "connection.authorize":
            return _response(request_id, result=connection.authorize_and_import().as_result())
        if capability == "connection.disconnect":
            return _response(request_id, result=connection.disconnect().as_result())
    except ConnectionError as error:
        return _response(request_id, error=str(error))
    return _response(request_id, error=f"unknown capability: {capability!r}")


def main() -> int:
    workspace = LocalWorkspace.open(workspace_root())
    connection = ConnectionService(
        workspace=workspace,
        vault=_vault(),
        oauth=GoogleOAuthGateway(),
    )
    try:
        for raw_request in sys.stdin:
            if not raw_request.strip():
                continue
            try:
                request = json.loads(raw_request)
            except json.JSONDecodeError:
                response: dict[str, object] = _response(None, error="invalid JSON request")
            else:
                if not isinstance(request, dict):
                    response = _response(None, error="request must be an object")
                else:
                    response = handle_request(request, workspace, connection)
            try:
                print(json.dumps(response, ensure_ascii=False), flush=True)
            except BrokenPipeError:
                _silence_broken_stdout()
                return 0
    except BrokenPipeError:
        _silence_broken_stdout()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        _silence_broken_stdout()
    except KeyboardInterrupt:
        pass
