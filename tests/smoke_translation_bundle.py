"""Run against a freshly built sidecar with local model and isolated user data.

Usage: uv run python tests/smoke_translation_bundle.py
"""

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from translation_fixture import source_from_prompt

from youtube_strataread.workbench.discovery import Candidate
from youtube_strataread.workbench.workspace import LocalWorkspace

calls = []


class Model(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        calls.append(body)
        content = body["messages"][-1]["content"]
        output = source_from_prompt(content)
        response = {
            "id": "chatcmpl-fixture",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "fixture",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": output},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
        }
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


with tempfile.TemporaryDirectory(prefix="edison-bundle-smoke-") as directory:
    root = Path(directory)
    model = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    state = root / "state"
    state.mkdir()
    (state / "prefs.json").write_text(json.dumps({"default_model": "deepseek:fixture"}))
    (state / "secrets.json").write_text(
        json.dumps(
            {
                "provider:deepseek": {
                    "api_key": "local-fixture",
                    "base_url": f"http://127.0.0.1:{model.server_port}/v1",
                }
            }
        )
    )
    ws = LocalWorkspace.open(root / "youtube")
    ws.add_candidate(
        Candidate(
            "fixture",
            "c",
            "C",
            "Packaged Chinese test",
            "https://youtube.com/watch?v=fixture",
            "2026-09-19",
            1,
        )
    )
    ws.store_transcript(
        "fixture",
        language="zh-Hant",
        srt_text="1\n00:00:00,000 --> 00:00:02,000\n這是繁體字幕，保留 42 個觀點。\n",
    )
    sources = {
        "short": "A source statement about 42 people.",
        "long": "A detailed statement about the project and its constraints. " * 220,
    }
    for video, source in sources.items():
        ws.add_candidate(
            Candidate(
                video, "c", "C", video, f"https://youtube.com/watch?v={video}", "2026-09-19", 1
            )
        )
        ws.store_transcript(
            video, language="en", srt_text=f"1\n00:00:00,000 --> 00:00:02,000\n{source}\n"
        )
    # These local fixtures represent already classified ordinary videos. Keep the
    # packaged translation smoke test independent of YouTube's live classifier.
    for video in ["fixture", *sources]:
        ws.set_preparation_state(video, "acquiring")
        ws.record_shorts_classification(video, False)
        ws.set_preparation_state(video, "queued")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    env = {
        **os.environ,
        "COWORKER_STATE_DIR": str(state),
        "YOUTUBE_WORKBENCH_WORKSPACE": str(root / "youtube"),
        "COWORKER_API_TOKEN": "local-smoke",
        "BY_PROMPTS_DIR": str(root / "prompts"),
    }
    with (root / "server.log").open("w") as log:
        proc = subprocess.Popen(
            [
                os.environ.get("EDISON_SIDECAR", "dist/openworker-server/openworker-server"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            client = httpx.Client(
                base_url=f"http://127.0.0.1:{port}",
                headers={"X-OpenWorker-Token": "local-smoke"},
                timeout=5,
            )
            for _ in range(60):
                if proc.poll() is not None:
                    raise RuntimeError("packaged server exited")
                try:
                    r = client.post(
                        "/v1/youtube/capability", json={"capability": "translation.settings"}
                    )
                    if r.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.5)
            assert r.json()["ok"], r.status_code
            assert r.json()["result"]["settings"]["max_tokens"] == 1500000
            for _ in range(60):
                asset = ws.asset("fixture")
                if asset["preparation_state"] in {"ready", "failed", "unavailable"}:
                    break
                time.sleep(0.5)
            assert asset["preparation_state"] == "ready", asset["failure_reason"]
            doc = ws.document("fixture")
            assert (
                Path(doc["translation_path"]).read_text().strip()
                == "这是繁体字幕，保留 42 个观点。"
            )
            for video, source in sources.items():
                for _ in range(120):
                    asset = ws.asset(video)
                    if asset["preparation_state"] in {"ready", "failed", "unavailable"}:
                        break
                    time.sleep(0.5)
                assert asset["preparation_state"] == "ready", asset["failure_reason"]
                document = ws.document(video)
                translated = Path(document["translation_path"]).read_text().strip()
                assert "".join(translated.split()) == "".join(source.split())
                provenance = json.loads(
                    Path(document["path"]).with_name("translation-run.json").read_text()
                )
                assert provenance["upstream"] == "e0fc605acbb5d78cb7a58a98bc8bd8f0056df49c"
            assert len(calls) > 10
            for pair in r.json()["result"]["settings"]["prompts"].values():
                for prompt in pair.values():
                    assert any("\u4e00" <= char <= "\u9fff" for char in prompt)
            for call in calls:
                for message in call["messages"]:
                    assert any("\u4e00" <= char <= "\u9fff" for char in message["content"])
                assert "You are an expert" not in call["messages"][0]["content"]
            print(
                json.dumps(
                    {
                        "packaged_backend": "passed",
                        "chinese_conversion": "passed",
                        "translation_artifact": "passed",
                        "model_requests": len(calls),
                    }
                )
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            model.shutdown()
