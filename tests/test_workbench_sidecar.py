from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_sidecar_serves_repeated_empty_library_snapshots(tmp_path: Path) -> None:
    workspace = tmp_path / "library"
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        "YOUTUBE_WORKBENCH_WORKSPACE": str(workspace),
        "YOUTUBE_WORKBENCH_TEST_VAULT": "1",
    }
    requests = "\n".join(
        [
            json.dumps({"id": "first", "capability": "library.snapshot", "arguments": {}}),
            json.dumps({"id": "second", "capability": "library.snapshot", "arguments": {}}),
            json.dumps({"id": "connection", "capability": "connection.status", "arguments": {}}),
            json.dumps(
                {
                    "id": "configure",
                    "capability": "connection.configure",
                    "arguments": {
                        "client_id": "desktop-client",
                        "client_secret": "not-a-real-secret",
                    },
                }
            ),
            json.dumps({"id": "configured", "capability": "connection.status", "arguments": {}}),
        ]
    )

    result = subprocess.run(
        [sys.executable, "-m", "youtube_strataread.workbench.sidecar"],
        input=f"{requests}\n",
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses == [
        {
            "id": "first",
            "ok": True,
            "result": {
                "workspace": {"label": "Local Library", "status": "ready"},
                "counts": {"inbox": 0, "to_read": 0, "reading": 0, "read": 0},
                "inbox": [],
            },
        },
        {
            "id": "second",
            "ok": True,
            "result": {
                "workspace": {"label": "Local Library", "status": "ready"},
                "counts": {"inbox": 0, "to_read": 0, "reading": 0, "read": 0},
                "inbox": [],
            },
        },
        {
            "id": "connection",
            "ok": True,
            "result": {
                "configured": False,
                "authorized": False,
                "subscription_count": 0,
            },
        },
        {
            "id": "configure",
            "ok": True,
            "result": {
                "configured": True,
                "authorized": False,
                "subscription_count": 0,
            },
        },
        {
            "id": "configured",
            "ok": True,
            "result": {
                "configured": True,
                "authorized": False,
                "subscription_count": 0,
            },
        },
    ]
    assert "not-a-real-secret" not in result.stdout
    assert workspace.is_dir()
