"""Verify a frozen release starts empty beside a populated legacy library.

Usage: uv run python tests/smoke_desktop_privacy.py [path/to/openworker-server]
Only synthetic records are created; no real user state or credentials are read.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from youtube_strataread.workbench.connection import SubscriptionSource
from youtube_strataread.workbench.discovery import Candidate
from youtube_strataread.workbench.workspace import LocalWorkspace


def check_release(binary: Path) -> None:
    forbidden = {"workspace.sqlite3", "secrets.json", "prefs.json", "desktop.json", ".env"}
    for path in binary.parent.rglob("*"):
        assert path.name not in forbidden and path.suffix not in {".sqlite", ".sqlite3", ".db"}, (
            f"User-state file in release: {path.relative_to(binary.parent)}"
        )
    with tempfile.TemporaryDirectory(prefix="edison-privacy-") as directory:
        root = Path(directory)
        # Seed the paths used by the old host and standalone YouTube application.
        legacy = root / "Library/Application Support/youtube-reading-workbench/workspace"
        ws = LocalWorkspace.open(legacy)
        ws.replace_subscription_sources([SubscriptionSource(channel_id="fixture", title="Private fixture")])
        ws.add_candidate(Candidate("fixture", "fixture", "Private fixture", "Private video",
                                   "https://youtube.com/watch?v=fixture", "2026-09-20", 1))
        ws.set_meta("drain_paused", "1")
        legacy_host = root / ".config/coworker"
        legacy_host.mkdir(parents=True)
        (legacy_host / "prefs.json").write_text('{"default_model":"private-fixture"}')
        def legacy_records():
            with sqlite3.connect(f"file:{ws.database_path}?mode=ro", uri=True) as db:
                return list(db.iterdump())

        before = legacy_records()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("COWORKER_", "YOUTUBE_WORKBENCH_"))}
        env.update(HOME=str(root), COWORKER_STATE_DIR=str(root / ".config/edison"),
                   COWORKER_API_TOKEN="fixture", YOUTUBE_WORKBENCH_AUTOMIC_VAULT="/usr/bin/false")
        with (root / "server.log").open("w") as log:
            proc = subprocess.Popen([str(binary.resolve()), "--host", "127.0.0.1", "--port", str(port)],
                                    env=env, cwd=root, stdout=log, stderr=log)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}",
                                  headers={"X-OpenWorker-Token": "fixture"}, timeout=2) as client:
                    def request(capability: str, **arguments):
                        response = client.post("/v1/youtube/capability", json={
                            "capability": capability, "arguments": arguments})
                        response.raise_for_status()
                        payload = response.json()
                        assert payload["ok"], "Release capability failed"
                        return payload["result"]

                    for _ in range(100):
                        assert proc.poll() is None, "Release exited before becoming ready"
                        try:
                            prefs = request("collection.preferences")
                            break
                        except httpx.HTTPError:
                            time.sleep(.2)
                    else:
                        raise AssertionError("Release did not become ready")
                    sources = len(prefs["sources"])
                    videos = request("activity.list", state="queued")["total"]
                    documents = request("library.list")["total"]
                    print(f"Release: {sources} subscriptions, {videos} videos, {documents} documents")
                    assert sources == videos == documents == 0, "Fresh release reads legacy personal data"
                    assert legacy_records() == before, "Release modified the legacy library"
            finally:
                proc.terminate()
                proc.wait(timeout=15)
    print("Release privacy smoke passed; legacy data unchanged")


if __name__ == "__main__":
    check_release(Path(sys.argv[1] if len(sys.argv) > 1 else "dist/openworker-server/openworker-server"))
