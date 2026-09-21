"""Swift-compatible records with atomic, one-way migration and archive restoration.

A CURRENT pointer publishes a fully validated generation (database + images) at once.
An interrupted import never replaces the previous generation. Original files are read only.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROMPT = """Create a realistic documentary-style 4:5 cover image for a private personal object archive.

Input: {{archivePhotoHint}}

Requirements: use only the provided archive photos as factual visual references, preserve the object's real form and materials, use a deep black or near-black background, restrained realistic still-life photography, no text, no watermark, no logo added by the image itself, no advertising composition."""
FIELDS = (
    "acquisitionSource",
    "brand",
    "material",
    "acquisitionDate",
    "model",
    "condition",
    "serialNumber",
    "metadataNote",
    "purchasePrice",
)
DEFAULT_FIELDS = ["acquisitionSource", "purchasePrice", "brand"]
MAX_IMAGE = 30 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def identity() -> str:
    return str(uuid.uuid4()).upper()


def safe_file(root: Path, relative: str) -> Path:
    if (
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ValueError("图片路径无效。")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError("图片路径无效。")
    return result


def decode_image(encoded: str) -> tuple[bytes, str]:
    if not isinstance(encoded, str) or len(encoded) > MAX_IMAGE * 4 // 3 + 100:
        raise ValueError("图片不能超过 30 MB。")
    try:
        data = base64.b64decode(encoded.split(",", 1)[-1], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("图片数据无效。") from error
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        ext = "jpg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        ext = "gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext = "webp"
    elif sys.platform == "darwin" and (
        data[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
        or data[4:8] == b"ftyp"
        or data[:2] == b"BM"
    ):
        # Match the original AppKit photo intake without adding a second imaging
        # runtime to the macOS bundle. Preserve source originals during migration;
        # convert only the rendering/upload copy of TIFF, HEIF/HEIC, AVIF or BMP.
        with tempfile.TemporaryDirectory(prefix="edison-object-photo-") as temporary:
            source = Path(temporary) / "photo"
            target = Path(temporary) / "photo.png"
            source.write_bytes(data)
            try:
                subprocess.run(
                    ["/usr/bin/sips", "-s", "format", "png", str(source), "--out", str(target)],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                data = target.read_bytes()
            except (subprocess.SubprocessError, OSError) as error:
                raise ValueError("无法读取这张照片，请尝试导出为 PNG 或 JPEG。") from error
        ext = "png"
    else:
        raise ValueError("请选择 PNG、JPEG、WebP 或 GIF 图片。")
    return data, ext


class ObjectLibrary:
    def __init__(self, root: Path, source: Path | None = None, preferences: Path | None = None):
        self.root = root.expanduser().resolve()
        self.source = (
            (source or Path.home() / "Library/Application Support/Minimalism")
            .expanduser()
            .resolve()
        )
        if (
            self.root == self.source
            or self.root.is_relative_to(self.source)
            or self.source.is_relative_to(self.root)
        ):
            raise ValueError("Edison 与原 Minimalism 资料目录必须独立。")
        self.preferences = preferences
        self.lock = threading.RLock()
        self.progress: dict[str, Any] = {"state": "idle", "completed": 0, "total": 0}

    @property
    def active(self) -> Path:
        name = (self.root / "CURRENT").read_text().strip()
        uuid.UUID(name)
        return self.root / "generations" / name

    @contextmanager
    def db(self, directory: Path | None = None):
        connection = sqlite3.connect((directory or self.active) / "Inventory.sqlite", timeout=30)
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _schema(self, directory: Path):
        with self.db(directory) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at REAL NOT NULL, deleted_at REAL);
                CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS edison_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    def _stage(self) -> Path:
        directory = self.root / "generations" / str(uuid.uuid4())
        directory.mkdir(parents=True, mode=0o700)
        (directory / "Covers").mkdir()
        return directory

    def _publish(self, directory: Path):
        previous = self.active if (self.root / "CURRENT").exists() else None
        pointer = self.root / "CURRENT.tmp"
        with pointer.open("w") as file:
            file.write(directory.name)
            file.flush()
            os.fsync(file.fileno())
        os.replace(pointer, self.root / "CURRENT")
        # Replacement is explicit. Do not retain an invisible second object library
        # that would resurrect records after a subsequent permanent deletion.
        if previous and previous != directory:
            shutil.rmtree(previous, ignore_errors=True)

    def _source_preferences(self) -> dict:
        # Read only whitelisted non-service preferences. Never access the old Keychain.
        candidates = (
            [self.preferences]
            if self.preferences
            else [
                Path.home() / "Library/Preferences/local.minimalism.app.plist",
                Path.home() / "Library/Preferences/Minimalism.plist",
            ]
        )
        for path in candidates:
            if path and path.is_file():
                with path.open("rb") as file:
                    raw = plistlib.load(file)
                return {
                    key: raw[key]
                    for key in (
                        "coverPromptTemplate",
                        "visibleMetadataFields",
                        "allObjectsRepresentativeAssetID",
                        "unfiledObjectsRepresentativeAssetID",
                    )
                    if key in raw
                }
        return {}

    def initialize(self):
        with self.lock:
            if (self.root / "CURRENT").exists():
                return
            self.progress = {"state": "copying", "completed": 0, "total": 0}
            stage = self._stage()
            try:
                source_db = self.source / "Inventory.sqlite"
                migrated = source_db.is_file()
                if migrated:
                    # SQLite's backup API includes committed WAL records consistently.
                    source = sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)
                    try:
                        with self.db(stage) as target:
                            source.backup(target)
                    finally:
                        source.close()
                    for folder in ("Covers", "Attachments"):
                        original = self.source / folder
                        files = list(original.rglob("*")) if original.exists() else []
                        self.progress["total"] += sum(p.is_file() for p in files)
                        for path in files:
                            if path.is_symlink():
                                raise ValueError("原资料包含外部文件链接，请检查后重试。")
                            if path.is_file():
                                destination = stage / folder / path.relative_to(original)
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(path, destination)
                                self.progress["completed"] += 1
                self._schema(stage)
                with self.db(stage) as db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("原资料库校验失败，原件未修改。")
                    assets, collections = self._records(db)
                    self._normalize(assets, collections)
                    self._validate_files(stage, assets, collections)
                    for table, records in (("assets", assets), ("collections", collections)):
                        for record in records:
                            self._write(db, table, record)
                    prefs = self._source_preferences()
                    self._set_meta(
                        db,
                        "preferences",
                        {
                            "coverPromptTemplate": prefs.get("coverPromptTemplate")
                            or DEFAULT_PROMPT,
                            "visibleMetadataFields": prefs.get(
                                "visibleMetadataFields", DEFAULT_FIELDS
                            ),
                            "allObjectsRepresentativeAssetID": prefs.get(
                                "allObjectsRepresentativeAssetID"
                            ),
                            "unfiledObjectsRepresentativeAssetID": prefs.get(
                                "unfiledObjectsRepresentativeAssetID"
                            ),
                        },
                    )
                    self._set_meta(
                        db,
                        "migration",
                        {
                            "completedAt": now(),
                            "imported": migrated,
                            "assets": len(assets),
                            "collections": len(collections),
                        },
                    )
                self._publish(stage)
                self.progress["state"] = "ready"
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                self.progress["state"] = "failed"
                raise

    @staticmethod
    def _records(db) -> tuple[list, list]:
        return tuple(
            [json.loads(row[0]) for row in db.execute(f"SELECT payload FROM {table}")]
            for table in ("assets", "collections")
        )

    @staticmethod
    def _normalize(assets: list, collections: list):
        ids = {c["id"] for c in collections}
        for record in [*assets, *collections]:
            uuid.UUID(record["id"])
            record.setdefault("createdAt", now())
            record.setdefault("updatedAt", record["createdAt"])
            record.setdefault("syncVersion", 1)
        for index, collection in enumerate(collections):
            collection.setdefault("role", "user")
            collection.setdefault("displayOrder", index)
        collections.sort(key=lambda c: (c["displayOrder"], c["createdAt"]))
        for index, collection in enumerate(collections):
            collection["displayOrder"] = index
        for asset in assets:
            if asset.get("collectionID") not in ids:
                asset["collectionID"] = None
            asset.setdefault("archivePhotoPaths", [])
            legacy = asset.get("archivePhotoPath")
            if legacy and legacy not in asset["archivePhotoPaths"]:
                asset["archivePhotoPaths"].insert(0, legacy)
            if "memoryBlocks" not in asset:
                asset["memoryBlocks"] = (
                    [
                        {
                            "id": identity(),
                            "text": asset["text"],
                            "createdAt": asset["updatedAt"],
                            "updatedAt": asset["updatedAt"],
                        }
                    ]
                    if asset.get("text", "").strip()
                    else []
                )
            asset.setdefault("customMetadata", {})
            asset.setdefault(
                "coverProvenance", "aiGenerated" if asset.get("coverImagePath") else "none"
            )
        by_id = {a["id"]: a for a in assets}
        for collection in collections:
            representative = by_id.get(collection.get("representativeAssetID"))
            if (
                not representative
                or representative.get("collectionID") != collection["id"]
                or representative.get("deletedAt")
                or not representative.get("coverImagePath")
            ):
                collection["representativeAssetID"] = None

    @staticmethod
    def _validate_files(directory: Path, assets: list, collections: list):
        for record in [*assets, *collections]:
            paths = [record.get("coverImagePath"), *record.get("archivePhotoPaths", [])]
            for relative in filter(None, paths):
                if not safe_file(directory / "Covers", relative).is_file():
                    raise ValueError("资料引用的图片缺失，请补齐原文件后重试。")

    @staticmethod
    def _write(db, table: str, record: dict):
        updated = datetime.fromisoformat(record["updatedAt"].replace("Z", "+00:00")).timestamp()
        payload = json.dumps(record, ensure_ascii=False)
        if table == "assets":
            deleted = record.get("deletedAt")
            deleted = (
                datetime.fromisoformat(deleted.replace("Z", "+00:00")).timestamp()
                if deleted
                else None
            )
            db.execute(
                "INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?)",
                (record["id"], payload, updated, deleted),
            )
        else:
            db.execute(
                "INSERT OR REPLACE INTO collections VALUES (?, ?, ?)",
                (record["id"], payload, updated),
            )

    @staticmethod
    def _set_meta(db, key, value):
        db.execute(
            "INSERT OR REPLACE INTO edison_meta VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    @staticmethod
    def _meta(db, key, default=None):
        row = db.execute("SELECT value FROM edison_meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def snapshot(self):
        self.initialize()
        with self.lock, self.db() as db:
            assets, collections = self._records(db)
            return {
                "assets": sorted(assets, key=lambda a: a["updatedAt"], reverse=True),
                "collections": sorted(collections, key=lambda c: c["displayOrder"]),
                "preferences": self._meta(db, "preferences"),
                "migration": self._meta(db, "migration"),
            }

    def mutate(self, action: str, args: dict):
        self.initialize()
        with self.lock, self.db() as db:
            assets, collections = self._records(db)
            if action == "preferences.save":
                prefs = self._meta(db, "preferences", {})
                incoming = args["preferences"]
                if "coverPromptTemplate" in incoming:
                    prompt = incoming["coverPromptTemplate"]
                    if not isinstance(prompt, str) or len(prompt) > 64000:
                        raise ValueError("封面提示词格式无效。")
                    prefs["coverPromptTemplate"] = prompt.strip() or DEFAULT_PROMPT
                if "visibleMetadataFields" in incoming:
                    fields = incoming["visibleMetadataFields"]
                    if not isinstance(fields, list) or any(f not in FIELDS for f in fields):
                        raise ValueError("元数据设置无效。")
                    prefs["visibleMetadataFields"] = fields
                for key in (
                    "allObjectsRepresentativeAssetID",
                    "unfiledObjectsRepresentativeAssetID",
                ):
                    if key in incoming:
                        value = incoming[key]
                        if value and not any(
                            a["id"] == value and a.get("coverImagePath") and not a.get("deletedAt")
                            for a in assets
                        ):
                            raise ValueError("请选择有封面的物品。")
                        prefs[key] = value
                self._set_meta(db, "preferences", prefs)
                return prefs
            if action == "collection.create":
                record = self._new(args.get("name"))
                record.update(role="user", displayOrder=len(collections))
                collections.append(record)
            elif action == "asset.create":
                record = self._new(args.get("name"))
                record.update(
                    memoryBlocks=[],
                    archivePhotoPaths=[],
                    coverProvenance="none",
                    customMetadata={},
                    collectionID=args.get("collectionID"),
                )
                assets.append(record)
            else:
                is_collection = action.startswith("collection.")
                records = collections if is_collection else assets
                record = next((r for r in records if r["id"] == args.get("id")), None)
                if record is None:
                    raise ValueError("该记录已不存在。")
                if is_collection and record.get("role") == "archive":
                    raise ValueError("归档集合不能修改或删除。")
                if action in ("asset.save", "collection.save"):
                    changes = args.get("changes", {})
                    allowed = (
                        {"name", "representativeAssetID"}
                        if is_collection
                        else {"name", "memoryBlocks", "customMetadata", "purchasePriceRMB", *FIELDS}
                        - {"purchasePrice"}
                    )
                    if set(changes) - allowed:
                        raise ValueError("不能修改这些字段。")
                    if "name" in changes:
                        self._valid_name(changes["name"])
                    if (
                        "purchasePriceRMB" in changes
                        and changes["purchasePriceRMB"] is not None
                        and (
                            type(changes["purchasePriceRMB"]) is not int
                            or changes["purchasePriceRMB"] < 0
                        )
                    ):
                        raise ValueError("价格须为非负整数人民币。")
                    if "memoryBlocks" in changes:
                        blocks = changes["memoryBlocks"]
                        if not isinstance(blocks, list) or any(
                            not isinstance(b, dict) or not isinstance(b.get("text"), str)
                            for b in blocks
                        ):
                            raise ValueError("记忆内容无效。")
                        for block in blocks:
                            block.setdefault("id", identity())
                            block.setdefault("createdAt", now())
                            block["updatedAt"] = now()
                        changes["text"] = "\n\n".join(
                            b["text"].strip() for b in blocks if b["text"].strip()
                        )
                    if "customMetadata" in changes and (
                        not isinstance(changes["customMetadata"], dict)
                        or any(
                            not isinstance(k, str) or not isinstance(v, str)
                            for k, v in changes["customMetadata"].items()
                        )
                    ):
                        raise ValueError("自定义元数据无效。")
                    record.update(changes)
                elif action == "collection.delete":
                    collections.remove(record)
                    db.execute("DELETE FROM collections WHERE id=?", (record["id"],))
                elif action == "collection.reorder":
                    target = max(0, min(int(args["position"]), len(collections) - 1))
                    collections.sort(key=lambda c: c.get("displayOrder", 0))
                    collections.remove(record)
                    collections.insert(target, record)
                    for index, collection in enumerate(collections):
                        collection["displayOrder"] = index
                elif action in ("asset.archive", "asset.unarchive", "asset.move"):
                    destination = args.get("collectionID")
                    if action == "asset.archive":
                        archive = next((c for c in collections if c.get("role") == "archive"), None)
                        if not archive:
                            archive = self._new("Archive")
                            archive.update(role="archive", displayOrder=len(collections))
                            collections.append(archive)
                        destination = archive["id"]
                    if destination and not any(c["id"] == destination for c in collections):
                        raise ValueError("集合不存在。")
                    record.update(collectionID=destination, deletedAt=None)
                elif action in ("asset.trash", "asset.restore"):
                    record["deletedAt"] = now() if action == "asset.trash" else None
                elif action == "asset.delete":
                    assets.remove(record)
                    db.execute("DELETE FROM assets WHERE id=?", (record["id"],))
                elif action == "asset.photo.add":
                    data, ext = decode_image(args["data"])
                    relative = f"{record['id']}/{identity()}.{ext}"
                    path = safe_file(self.active / "Covers", relative)
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(data)
                    record["archivePhotoPaths"].append(relative)
                elif action == "asset.photo.remove":
                    record["archivePhotoPaths"] = [
                        p for p in record["archivePhotoPaths"] if p != args["path"]
                    ]
                    record.pop("archivePhotoPath", None)
                elif action == "asset.cover.remove":
                    record.update(coverImagePath=None, coverProvenance="none")
                elif action == "asset.cover.apply":
                    preview = safe_file(self.active / "Pending", args["preview"])
                    # Tokens are bound to the object, never accepted as arbitrary cover files.
                    if preview.parent.name != record["id"] or not preview.is_file():
                        raise ValueError("封面预览已失效，请重新生成。")
                    relative = f"{record['id']}/{preview.name}"
                    dest = safe_file(self.active / "Covers", relative)
                    dest.parent.mkdir(exist_ok=True)
                    shutil.copy2(preview, dest)
                    record.update(coverImagePath=relative, coverProvenance="aiGenerated")
                else:
                    raise ValueError("未知物品操作。")
                record["updatedAt"] = now()
                record["syncVersion"] = record.get("syncVersion", 0) + 1
            self._normalize(assets, collections)
            for table, records in (("assets", assets), ("collections", collections)):
                for item in records:
                    self._write(db, table, item)
            db.commit()
            self._collect_unused_images(assets, collections)
            return record

    @staticmethod
    def _valid_name(name):
        if not isinstance(name, str) or not name.strip() or len(name) > 1000:
            raise ValueError("请输入物品或集合名称。")

    def _new(self, name):
        self._valid_name(name)
        return {
            "id": identity(),
            "name": name.strip(),
            "createdAt": now(),
            "updatedAt": now(),
            "syncVersion": 1,
        }

    def _collect_unused_images(self, assets, collections):
        used = {
            p
            for r in [*assets, *collections]
            for p in [r.get("coverImagePath"), *r.get("archivePhotoPaths", [])]
            if p
        }
        for file in (self.active / "Covers").rglob("*"):
            if file.is_file() and file.relative_to(self.active / "Covers").as_posix() not in used:
                file.unlink()
        retained = {a["id"] for a in assets}
        attachments = self.active / "Attachments"
        if attachments.is_dir():
            for directory in attachments.iterdir():
                if directory.is_dir() and directory.name not in retained:
                    shutil.rmtree(directory)

    def image(self, relative: str):
        self.initialize()
        with self.lock:
            path = safe_file(self.active / "Covers", relative)
            if not path.is_file():
                raise ValueError("图片不存在。")
            encoded = base64.b64encode(path.read_bytes()).decode()
            data, ext = decode_image(encoded)
            return {
                "data": base64.b64encode(data).decode(),
                "mime": "image/jpeg" if ext == "jpg" else f"image/{ext}",
            }

    def export(self) -> bytes:
        with self.lock:
            snapshot = self.snapshot()
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for table in ("assets", "collections"):
                    archive.writestr(
                        table + ".json", json.dumps(snapshot[table], ensure_ascii=False)
                    )
                archive.writestr(
                    "preferences.json", json.dumps(snapshot["preferences"], ensure_ascii=False)
                )
                for folder in ("Covers", "Attachments"):
                    for path in (self.active / folder).rglob("*"):
                        if path.is_file():
                            archive.write(path, path.relative_to(self.active).as_posix())
            return output.getvalue()

    def restore_directory(self, path: str):
        """Import the original macOS .minimalism directory package without changing it."""
        source = Path(path).expanduser().resolve()
        if not source.is_dir() or not (source / "assets.json").is_file():
            raise ValueError("请选择包含 assets.json 的 Minimalism 备份文件夹。")
        output = io.BytesIO()
        total = 0
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            files = [
                source / "assets.json",
                source / "collections.json",
                source / "preferences.json",
            ]
            files.extend((source / "Covers").rglob("*"))
            for file in files:
                if file.is_symlink():
                    raise ValueError("备份不能包含外部文件链接。")
                if file.is_file():
                    total += file.stat().st_size
                    if total > 2 * 1024**3:
                        raise ValueError("备份过大。")
                    archive.write(file, file.relative_to(source).as_posix())
        return self.restore(output.getvalue())

    def export_directory(self, path: str):
        """Save a native backup package inside the explicitly selected destination."""
        destination = Path(path).expanduser().resolve()
        if not destination.is_dir():
            raise ValueError("请选择备份保存文件夹。")
        name = f"Minimalism-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.minimalism"
        stage = Path(tempfile.mkdtemp(prefix=".minimalism-backup-", dir=destination))
        try:
            with zipfile.ZipFile(io.BytesIO(self.export())) as archive:
                # The archive is produced by this library, not by an external input.
                archive.extractall(stage)
            stage.rename(destination / name)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return {"name": name}

    def restore(self, data: bytes):
        self.initialize()
        with self.lock:
            stage = self._stage()
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    if (
                        sum(i.file_size for i in archive.infolist()) > 2 * 1024**3
                        or len(archive.infolist()) > 50000
                    ):
                        raise ValueError("备份过大。")
                    for info in archive.infolist():
                        path = safe_file(stage, info.filename.rstrip("/"))
                        if info.is_dir():
                            continue
                        if info.filename not in (
                            "assets.json",
                            "collections.json",
                            "preferences.json",
                        ) and not info.filename.startswith(("Covers/", "Attachments/")):
                            continue
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as source, path.open("wb") as target:
                            shutil.copyfileobj(source, target)
                assets = json.loads((stage / "assets.json").read_text())
                collections = (
                    json.loads((stage / "collections.json").read_text())
                    if (stage / "collections.json").exists()
                    else []
                )
                if not isinstance(assets, list) or not isinstance(collections, list):
                    raise ValueError("备份格式无效。")
                for records in (assets, collections):
                    if len({r["id"] for r in records}) != len(records):
                        raise ValueError("备份包含重复记录。")
                self._normalize(assets, collections)
                self._validate_files(stage, assets, collections)
                self._schema(stage)
                with self.db(stage) as db:
                    for table, records in (("assets", assets), ("collections", collections)):
                        for record in records:
                            self._write(db, table, record)
                    prefs = self.snapshot()["preferences"]
                    prefs_file = stage / "preferences.json"
                    if prefs_file.exists():
                        incoming = json.loads(prefs_file.read_text())
                        prefs = {key: incoming.get(key, value) for key, value in prefs.items()}
                    self._set_meta(db, "preferences", prefs)
                    self._set_meta(db, "migration", {"completedAt": now(), "restored": True})
                self._publish(stage)
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                raise
        return self.snapshot()
