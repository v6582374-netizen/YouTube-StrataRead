"""Line-oriented capability sidecar for the local desktop workbench."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from youtube_strataread.workbench.connection import (
    ConnectionError,
    ConnectionService,
    GoogleOAuthGateway,
)
from youtube_strataread.workbench.discovery import SubscriptionDiscovery, YouTubeAtomFeeds
from youtube_strataread.workbench.library import (
    AutomaticBatch,
    ConfiguredManuscripts,
    LibraryService,
    PreparationService,
    YtDlpCaptions,
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
    discovery: SubscriptionDiscovery,
    library: LibraryService | None = None,
) -> dict[str, object]:
    request_id = request.get("id")
    capability = request.get("capability")
    arguments = request.get("arguments", {})
    if not isinstance(arguments, dict):
        return _response(request_id, error="arguments must be an object")
    try:
        if capability == "library.snapshot":
            return _response(request_id, result=workspace.snapshot().as_result())
        if library is not None and capability == "library.list":
            return _response(request_id, result=library.list_assets(**_filters(arguments)))
        if library is not None and capability == "library.search":
            return _response(request_id, result=library.search(**_filters(arguments)))
        if library is not None and capability == "library.inspect":
            return _response(request_id, result=library.inspect(_video_id(arguments)))
        if library is not None and capability == "library.set_reading_state":
            return _response(
                request_id,
                result=library.set_reading_state(
                    _video_id(arguments), str(arguments.get("reading_state") or "")
                ),
            )
        if library is not None and capability == "library.regenerate":
            return _response(request_id, result=library.regenerate(_video_id(arguments)))
        if library is not None and capability == "library.delete":
            return _response(request_id, result=library.delete(_video_id(arguments)))
        if library is not None and capability == "documents.get":
            return _response(request_id, result=library.document(_video_id(arguments)))
        if library is not None and capability == "activity.snapshot":
            return _response(request_id, result=library.activity())
        if library is not None and capability == "diagnostics.snapshot":
            return _response(request_id, result=library.activity())
        if library is not None and capability == "activity.drain_pause":
            return _response(request_id, result=library.drain_pause())
        if library is not None and capability == "activity.resume":
            return _response(request_id, result=library.resume())
        if library is not None and capability == "activity.retry":
            return _response(request_id, result=library.retry(_video_id(arguments)))
        if library is not None and capability == "activity.retry_all_failed":
            return _response(request_id, result=library.retry_all_failed())
        if capability == "connection.status":
            return _response(request_id, result=connection.status().as_result())
        if capability == "collection.subscription_sources":
            return _response(request_id, result={"sources": connection.subscription_sources()})
        if capability == "collection.refresh_updates":
            return _response(request_id, result=discovery.refresh().as_result())
        if capability == "collection.backfill_updates":
            return _response(
                request_id,
                result=discovery.backfill(
                    days=int(arguments.get("days") or 7),
                    limit=int(arguments.get("limit") or 100),
                ).as_result(),
            )
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
    except (ConnectionError, KeyError, ValueError) as error:
        return _response(request_id, error=str(error))
    return _response(request_id, error=f"unknown capability: {capability!r}")


def _video_id(arguments: Mapping[str, Any]) -> str:
    value = str(arguments.get("video_id") or "").strip()
    if not value:
        raise ValueError("video_id is required")
    return value


def _filters(arguments: Mapping[str, Any]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in ("query", "reading_state", "channel_id", "preparation_state"):
        value = arguments.get(name)
        if value is not None:
            result[name] = str(value)
    for name in ("published_after", "published_before"):
        value = arguments.get(name)
        if value is not None:
            result[name] = float(value)
    for flag in ("include_transcript", "documents_only", "unread_only"):
        result[flag] = bool(arguments.get(flag, False))
    return result


def _run_batch(
    preparation: PreparationService, discovery: SubscriptionDiscovery, stop: threading.Event
) -> None:
    """Keep automatic work quiet and serial; all observable state lives in SQLite."""
    batch = AutomaticBatch(preparation=preparation)
    next_discovery = 0.0
    while not stop.wait(0.5):
        try:
            if time.monotonic() >= next_discovery:
                next_discovery = time.monotonic() + 15 * 60
                discovery.refresh()
                batch.reset()
            batch.run_one()
        except Exception:
            # A top-level guard keeps one malformed local asset from killing the service.
            time.sleep(0.5)


def main() -> int:
    workspace = LocalWorkspace.open(workspace_root())
    connection = ConnectionService(
        workspace=workspace,
        vault=_vault(),
        oauth=GoogleOAuthGateway(),
    )
    discovery = SubscriptionDiscovery(workspace=workspace, feeds=YouTubeAtomFeeds())
    preparation = PreparationService(
        workspace=workspace, captions=YtDlpCaptions(), manuscripts=ConfiguredManuscripts()
    )
    library = LibraryService(workspace=workspace, preparation=preparation)
    stop_batch = threading.Event()
    batch = threading.Thread(
        target=_run_batch, args=(preparation, discovery, stop_batch), daemon=True
    )
    batch.start()
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
                    response = handle_request(request, workspace, connection, discovery, library)
            try:
                print(json.dumps(response, ensure_ascii=False), flush=True)
            except BrokenPipeError:
                _silence_broken_stdout()
                return 0
    except BrokenPipeError:
        _silence_broken_stdout()
    except KeyboardInterrupt:
        pass
    finally:
        stop_batch.set()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        _silence_broken_stdout()
    except KeyboardInterrupt:
        pass
