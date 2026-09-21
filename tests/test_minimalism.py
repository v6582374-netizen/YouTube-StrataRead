"""Source-compatible records exercised through the actual authenticated desktop boundary."""

import base64
import hashlib
import io
import json
import plistlib
import sqlite3
import zipfile
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coworker.minimalism.images import ImageService
from coworker.minimalism.store import ObjectLibrary, identity, now
from coworker.server.minimalism import attach_minimalism

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAFCAIAAADtz9qMAAAAEUlEQVR4nGNYsWQGHDGQwQEAzqUl0cr1W6MAAAAASUVORK5CYII="
)


class Secrets:
    def __init__(self):
        self.profiles = {}

    def get(self, key):
        return self.profiles.get(key)

    def put(self, key, value):
        self.profiles[key] = value


@pytest.fixture
def source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    collection = {
        "id": identity(),
        "name": "日常",
        "role": "user",
        "createdAt": now(),
        "updatedAt": now(),
        "displayOrder": 0,
    }
    asset_id = identity()
    photo = f"{asset_id}/photo.png"
    asset = {
        "id": asset_id,
        "name": "旧相机",
        "text": "旧版记忆",
        "collectionID": collection["id"],
        "coverImagePath": photo,
        "archivePhotoPath": photo,
        "purchasePriceRMB": 2300,
        "createdAt": now(),
        "updatedAt": now(),
        "customMetadata": {"镜头": "35 mm"},
        "unknownFutureField": {"preserve": True},
    }
    db = sqlite3.connect(source / "Inventory.sqlite")
    db.executescript(
        "CREATE TABLE assets(id TEXT PRIMARY KEY,payload TEXT,updated_at REAL,deleted_at REAL); CREATE TABLE collections(id TEXT PRIMARY KEY,payload TEXT,updated_at REAL);"
    )
    db.execute("INSERT INTO assets VALUES (?,?,?,NULL)", (asset_id, json.dumps(asset), 0))
    db.execute(
        "INSERT INTO collections VALUES (?,?,?)", (collection["id"], json.dumps(collection), 0)
    )
    db.commit()
    db.close()
    path = source / "Covers" / photo
    path.parent.mkdir(parents=True)
    path.write_bytes(PNG)
    preferences = tmp_path / "preferences.plist"
    preferences.write_bytes(
        plistlib.dumps(
            {
                "coverPromptTemplate": "Only {{archivePhotoHint}}",
                "imageBaseURL": "https://old.example/v1",
                "imageModel": "old-model",
                "imageAPIKey": "DO-NOT-IMPORT",
            }
        )
    )
    return source, preferences, asset, collection


@pytest.fixture
def library(tmp_path, source):
    return ObjectLibrary(tmp_path / "edison", source[0], source[1])


def test_migration_is_lazy_lossless_once_and_source_untouched(library, source):
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source[0].rglob("*")
        if p.is_file()
    }
    assert not library.root.exists()
    data = library.snapshot()
    asset = data["assets"][0]
    assert asset["memoryBlocks"][0]["text"] == "旧版记忆"
    assert asset["unknownFutureField"] == {"preserve": True}
    assert asset["archivePhotoPaths"] == [source[2]["archivePhotoPath"]]
    assert data["preferences"]["coverPromptTemplate"] == "Only {{archivePhotoHint}}"
    assert "old-model" not in json.dumps(data) and "DO-NOT-IMPORT" not in json.dumps(data)
    library.mutate("asset.save", {"id": asset["id"], "changes": {"name": "Edison 内修改"}})
    again = ObjectLibrary(library.root, source[0], source[1]).snapshot()
    assert len(again["assets"]) == 1 and again["assets"][0]["name"] == "Edison 内修改"
    assert {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source[0].rglob("*")
        if p.is_file()
    } == before


def test_failed_import_never_publishes_partial_dataset_and_retries(library, source):
    photo = source[0] / "Covers" / source[2]["archivePhotoPath"]
    photo.unlink()
    with pytest.raises(ValueError, match="图片缺失"):
        library.snapshot()
    assert not (library.root / "CURRENT").exists()
    photo.write_bytes(PNG)
    assert len(library.snapshot()["assets"]) == 1


def test_committed_wal_is_migrated(library, source):
    db = sqlite3.connect(source[0] / "Inventory.sqlite")
    db.execute("PRAGMA journal_mode=WAL")
    asset = dict(source[2], name="在 WAL 中")
    db.execute("UPDATE assets SET payload=?", (json.dumps(asset),))
    db.commit()
    assert library.snapshot()["assets"][0]["name"] == "在 WAL 中"
    db.close()


def test_object_collection_archive_photo_and_backup_lifecycles(library):
    initial = library.snapshot()
    asset = initial["assets"][0]
    collection = initial["collections"][0]
    library.mutate(
        "collection.save",
        {"id": collection["id"], "changes": {"representativeAssetID": asset["id"]}},
    )
    library.mutate("asset.archive", {"id": asset["id"]})
    archived = library.snapshot()
    assert archived["assets"][0]["collectionID"] == next(
        c["id"] for c in archived["collections"] if c["role"] == "archive"
    )
    assert (
        next(c for c in archived["collections"] if c["id"] == collection["id"])[
            "representativeAssetID"
        ]
        is None
    )
    with pytest.raises(ValueError):
        library.mutate("collection.delete", {"id": archived["assets"][0]["collectionID"]})
    library.mutate("asset.unarchive", {"id": asset["id"]})
    assert library.snapshot()["assets"][0]["collectionID"] is None
    library.mutate("asset.move", {"id": asset["id"], "collectionID": collection["id"]})
    library.mutate("collection.delete", {"id": collection["id"]})
    assert library.snapshot()["assets"][0]["collectionID"] is None
    library.mutate("asset.photo.add", {"id": asset["id"], "data": base64.b64encode(PNG).decode()})
    library.mutate(
        "asset.save",
        {
            "id": asset["id"],
            "changes": {
                "memoryBlocks": [{"text": "新的独立记忆"}],
                "customMetadata": {"测试": "保留"},
            },
        },
    )
    backup = library.export()
    library.mutate("asset.delete", {"id": asset["id"]})
    assert not library.snapshot()["assets"]
    restored = library.restore(backup)
    assert restored["assets"][0]["memoryBlocks"][0]["text"] == "新的独立记忆"
    assert len(restored["assets"][0]["archivePhotoPaths"]) == 2
    assert library.image(asset["coverImagePath"])["data"] == base64.b64encode(PNG).decode()


def test_invalid_restore_keeps_current_records_and_images(library):
    before = library.snapshot()
    active = library.active
    for path in ("../escape", "assets.json"):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(path, "not JSON")
        with pytest.raises((ValueError, KeyError)):
            library.restore(output.getvalue())
        assert library.active == active
        assert library.snapshot() == before


def test_legacy_backup_without_collections(library):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "assets.json", json.dumps([{"id": identity(), "name": "Legacy", "text": "记忆"}])
        )
    restored = library.restore(output.getvalue())
    assert restored["assets"][0]["memoryBlocks"][0]["text"] == "记忆"
    assert restored["collections"] == []


def test_image_configuration_and_preview_apply_are_separate(library, monkeypatch):
    secrets = Secrets()
    service = ImageService(secrets)
    asset = library.snapshot()["assets"][0]
    with pytest.raises(ValueError, match="配置"):
        service.generate(library, asset["id"])
    assert service.save(
        {
            "base_url": "https://new.example/v1",
            "model": "image-model",
            "api_key": "private-test-key",
        }
    )["ready"]
    assert "private-test-key" not in json.dumps(service.settings())
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    client_class = httpx.Client
    monkeypatch.setattr(
        "coworker.minimalism.images.httpx.Client",
        lambda **kw: client_class(transport=httpx.MockTransport(response), **kw),
    )
    preview = service.generate(library, asset["id"])
    assert library.snapshot()["assets"][0]["coverImagePath"] == asset["coverImagePath"]
    assert requests[0].url.path == "/v1/images/edits"
    assert b"One factual archive photo" in requests[0].content
    assert "旧相机".encode() not in requests[0].content
    other = library.mutate("asset.create", {"name": "Other"})
    with pytest.raises(ValueError):
        library.mutate("asset.cover.apply", {"id": other["id"], "preview": preview["preview"]})
    library.mutate("asset.cover.apply", {"id": asset["id"], "preview": preview["preview"]})
    assert library.snapshot()["assets"][0]["coverImagePath"] != asset["coverImagePath"]
    service.generate(library, other["id"])
    assert requests[-1].url.path == "/v1/images/generations"
    assert "private-test-key" not in library.export().decode("latin1")


def test_http_boundary_laziness_settings_and_failure(tmp_path, source, monkeypatch):
    monkeypatch.setenv("EDISON_MINIMALISM_WORKSPACE", str(tmp_path / "api-library"))
    monkeypatch.setenv("EDISON_MINIMALISM_SOURCE", str(source[0]))
    monkeypatch.setenv("EDISON_MINIMALISM_PREFERENCES", str(source[1]))
    app = FastAPI()
    attach_minimalism(app, SimpleNamespace(secrets=Secrets()))
    with TestClient(app) as client:
        assert (
            client.post("/v1/minimalism/capability", json={"capability": "image.settings"}).json()[
                "result"
            ]["ready"]
            is False
        )
        assert not app.state.minimalism.root.exists()
        data = client.post(
            "/v1/minimalism/capability", json={"capability": "library.snapshot"}
        ).json()
        assert data["ok"] and data["result"]["assets"][0]["name"] == "旧相机"
        assert not client.post(
            "/v1/minimalism/capability",
            json={"capability": "image.get", "arguments": {"path": "../../preferences.plist"}},
        ).json()["ok"]
        archive = client.get("/v1/minimalism/backup")
        assert archive.status_code == 200
        assert client.post("/v1/minimalism/restore", content=archive.content).status_code == 200


def test_collection_order_remains_contiguous_after_removal(library):
    first = library.snapshot()["collections"][0]
    second = library.mutate("collection.create", {"name": "Second"})
    third = library.mutate("collection.create", {"name": "Third"})
    library.mutate("collection.delete", {"id": first["id"]})
    assert [c["displayOrder"] for c in library.snapshot()["collections"]] == [0, 1]
    library.mutate("collection.reorder", {"id": third["id"], "position": 0})
    assert [c["id"] for c in library.snapshot()["collections"]] == [third["id"], second["id"]]


def test_original_directory_backup_and_permanent_attachment_deletion(library, tmp_path):
    snapshot = library.snapshot()
    source = tmp_path / "legacy.minimalism"
    source.mkdir()
    with zipfile.ZipFile(io.BytesIO(library.export())) as archive:
        archive.extractall(source)
    # The original directory format has no Edison preferences or credentials.
    (source / "preferences.json").unlink()
    previous = library.active
    restored = library.restore_directory(str(source))
    assert restored["assets"] == snapshot["assets"]
    assert not previous.exists()
    asset_id = restored["assets"][0]["id"]
    attachments = library.active / "Attachments" / asset_id
    attachments.mkdir(parents=True)
    (attachments / "legacy.txt").write_text("private attachment")
    library.mutate("asset.delete", {"id": asset_id})
    assert not attachments.exists()
