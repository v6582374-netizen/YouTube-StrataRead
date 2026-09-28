"""Exercise the frozen server's actual macOS Keychain adapter with disposable data."""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

binary = Path(
    sys.argv[1] if len(sys.argv) > 1 else "dist/openworker-server/openworker-server"
).resolve()
with tempfile.TemporaryDirectory(prefix="edison-keychain-smoke-") as directory:
    root = Path(directory)
    workspace = root / "youtube"
    account = hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COWORKER_", "YOUTUBE_WORKBENCH_", "EDISON_GOOGLE_"))
    }
    env.update(
        COWORKER_STATE_DIR=str(root / "host"),
        COWORKER_SCRATCH_BASE=str(root / "scratch"),
        YOUTUBE_WORKBENCH_WORKSPACE=str(workspace),
        COWORKER_API_TOKEN="local-keychain-smoke",
        YOUTUBE_WORKBENCH_AUTOMIC_VAULT=str(root / "vault-must-not-be-used"),
    )
    written = False
    try:
        for launch in range(2):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            with (root / "server.log").open("w") as log:
                proc = subprocess.Popen(
                    [str(binary), "--host", "127.0.0.1", "--port", str(port)],
                    env=env,
                    cwd=root,
                    stdout=log,
                    stderr=log,
                )
                try:
                    with httpx.Client(
                        base_url=f"http://127.0.0.1:{port}",
                        headers={"X-OpenWorker-Token": "local-keychain-smoke"},
                        timeout=30,
                    ) as client:
                        for _ in range(100):
                            assert proc.poll() is None, "Frozen server exited"
                            try:
                                if client.get("/v1/health").status_code == 200:
                                    break
                            except httpx.HTTPError:
                                pass
                            time.sleep(0.2)

                        def call(capability, **arguments):
                            response = client.post(
                                "/v1/youtube/capability",
                                json={"capability": capability, "arguments": arguments},
                            )
                            response.raise_for_status()
                            payload = response.json()
                            assert payload["ok"], payload.get("error")
                            return payload["result"]

                        assert call("connection.status")["configured"] == bool(launch)
                        call(
                            "connection.configure",
                            client_id="keychain-smoke-client",
                            client_secret="synthetic-keychain-smoke-secret",
                        )
                        written = True
                        for _ in range(3):
                            state = call("connection.status")
                            assert state["configured"] and not state["authorized"]
                        print(
                            f"Frozen Keychain launch {launch + 1}: configure and repeated status passed"
                        )
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
    finally:
        if written:
            # Delete the disposable item by attributes, without asking a different
            # executable (the test runner) to read the frozen app's private data.
            subprocess.run(["/usr/bin/security", "delete-generic-password", "-s",
                            "netizen.v6582374.edison.youtube", "-a", account],
                           check=True, capture_output=True)
            print("Disposable Keychain record removed")
