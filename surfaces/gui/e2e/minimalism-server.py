"""Isolated real Edison backend for the Minimalism browser E2E.

Only the external paid image provider is simulated. All object/settings/backup
requests go through the actual host auth, routes, SQLite and image service.
"""

import json
import os
import plistlib
import socket
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

root = Path(sys.argv[1])
os.environ.update(
    COWORKER_STATE_DIR=str(root / "host"),
    COWORKER_API_TOKEN="minimalism-e2e-token",
    EDISON_MINIMALISM_WORKSPACE=str(root / "objects"),
    EDISON_MINIMALISM_SOURCE=str(root / "source"),
    EDISON_MINIMALISM_PREFERENCES=str(root / "old.plist"),
    YOUTUBE_WORKBENCH_WORKSPACE=str(root / "youtube"),
)

import uvicorn  # noqa: E402

from coworker.minimalism.store import identity, now  # noqa: E402
from coworker.server import SessionManager, create_app  # noqa: E402

png = "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAFCAIAAADtz9qMAAAAEUlEQVR4nGNYsWQGHDGQwQEAzqUl0cr1W6MAAAAASUVORK5CYII="
source = root / "source"
source.mkdir()
asset = {
    "id": identity(),
    "name": "迁入的相机",
    "memoryBlocks": [
        {"id": identity(), "text": "带去京都的相机", "createdAt": now(), "updatedAt": now()}
    ],
    "archivePhotoPaths": [],
    "createdAt": now(),
    "updatedAt": now(),
    "purchasePriceRMB": 2400,
    "customMetadata": {"镜头": "35mm"},
}
with sqlite3.connect(source / "Inventory.sqlite") as db:
    db.executescript(
        "CREATE TABLE assets(id TEXT PRIMARY KEY,payload TEXT,updated_at REAL,deleted_at REAL); CREATE TABLE collections(id TEXT PRIMARY KEY,payload TEXT,updated_at REAL);"
    )
    db.execute("INSERT INTO assets VALUES (?,?,0,NULL)", (asset["id"], json.dumps(asset)))
(root / "old.plist").write_bytes(
    plistlib.dumps(
        {
            "coverPromptTemplate": "Preserve the object. {{archivePhotoHint}}",
            "imageModel": "old-model-must-not-migrate",
        }
    )
)


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        data = self.rfile.read(int(self.headers["Content-Length"]))
        with (root / "provider-calls.jsonl").open("a") as f:
            f.write(json.dumps({"path": self.path, "reference": b"image[]" in data}) + "\n")
        body = json.dumps({"data": [{"b64_json": png}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
threading.Thread(target=provider.serve_forever, daemon=True).start()
manager = SessionManager(data_dir=root / "host")
app = create_app(manager)
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(json.dumps({"port": sock.getsockname()[1], "provider": provider.server_port}), flush=True)
server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
server.run(sockets=[sock])
