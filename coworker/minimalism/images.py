"""Image generation uses the host SecretStore, never the source application's keys."""

from __future__ import annotations

import base64
import threading
from urllib.parse import urlsplit

import httpx

from .store import DEFAULT_PROMPT, ObjectLibrary, decode_image, identity, safe_file

PROFILE = "image_generation:default"


class ImageService:
    def __init__(self, secrets):
        self.secrets = secrets
        self.lock = threading.Lock()
        self.running: set[str] = set()

    def settings(self):
        config = self.secrets.get(PROFILE) or {}
        return {
            "base_url": config.get("base_url", ""),
            "model": config.get("model", ""),
            "has_key": bool(config.get("api_key")),
            "ready": all(config.get(k) for k in ("base_url", "model", "api_key")),
        }

    def save(self, values):
        with self.lock:
            config = dict(self.secrets.get(PROFILE) or {})
            for key in ("base_url", "model", "api_key"):
                if key in values:
                    value = values[key]
                    if not isinstance(value, str) or len(value) > 16000:
                        raise ValueError("图像生成配置无效。")
                    if key != "api_key" or value.strip():
                        config[key] = value.strip()
            if values.get("clear_key"):
                config.pop("api_key", None)
            url = urlsplit(config.get("base_url", ""))
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("请输入有效的 API Base URL。")
            if not config.get("model"):
                raise ValueError("请输入图像模型名称。")
            config["base_url"] = config["base_url"].rstrip("/")
            self.secrets.put(PROFILE, config)
        return self.settings()

    def generate(self, library: ObjectLibrary, asset_id: str):
        if not self.settings()["ready"]:
            raise ValueError("请先在 Edison 设置中配置图像生成服务。")
        with self.lock:
            if asset_id in self.running:
                raise ValueError("该物品正在生成封面。")
            self.running.add(asset_id)
        try:
            with library.lock:
                snapshot = library.snapshot()
                asset = next((a for a in snapshot["assets"] if a["id"] == asset_id), None)
                if not asset:
                    raise ValueError("物品不存在。")
                generation = library.active
                photos = asset.get("archivePhotoPaths", [])[:4]
                images = []
                for relative in photos:
                    path = safe_file(generation / "Covers", relative)
                    photo = library.image(relative)
                    images.append(
                        (
                            "image[]",
                            (
                                path.stem
                                + (
                                    ".jpg"
                                    if photo["mime"] == "image/jpeg"
                                    else "." + photo["mime"].split("/")[-1]
                                ),
                                base64.b64decode(photo["data"]),
                                photo["mime"],
                            ),
                        )
                    )
                hint = (
                    "One factual archive photo is available as visual reference."
                    if len(images) == 1
                    else f"{len(images)} factual archive photos are available as visual references."
                    if images
                    else "No archive photo is available; rely on the built-in visual direction only."
                )
                prompt = (
                    snapshot["preferences"].get("coverPromptTemplate") or DEFAULT_PROMPT
                ).replace("{{archivePhotoHint}}", hint)
            config = self.secrets.get(PROFILE) or {}
            fields = {
                "model": config["model"],
                "prompt": prompt,
                "n": "1",
                "quality": "high",
                "moderation": "auto",
            }
            with httpx.Client(timeout=180, follow_redirects=False) as client:
                headers = {"Authorization": "Bearer " + config["api_key"]}
                if images:
                    fields.update(
                        size="1024x1536",
                        output_format="png",
                        input_fidelity="high",
                        background="opaque",
                    )
                    response = client.post(
                        config["base_url"] + "/images/edits",
                        headers=headers,
                        data=fields,
                        files=images,
                    )
                else:
                    response = client.post(
                        config["base_url"] + "/images/generations",
                        headers=headers,
                        json={
                            **fields,
                            "n": 1,
                            "ratio": "4:5",
                            "size": "2K",
                            "response_format": "b64_json",
                        },
                    )
                response.raise_for_status()
                encoded = response.json()["data"][0]["b64_json"]
                data, ext = decode_image(encoded)
            with library.lock:
                if library.active != generation or not any(
                    a["id"] == asset_id for a in library.snapshot()["assets"]
                ):
                    raise ValueError("资料已变化，本次生成未应用。")
                token = f"{asset_id}/{identity()}.{ext}"
                path = safe_file(generation / "Pending", token)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            return {
                "preview": token,
                "data": base64.b64encode(data).decode(),
                "mime": "image/jpeg" if ext == "jpg" else f"image/{ext}",
                "used_reference": bool(images),
            }
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as error:
            # Provider bodies can echo a credential or private prompt. Do not expose them.
            raise ValueError("封面生成失败，请检查图像服务配置后重试。") from error
        finally:
            with self.lock:
                self.running.discard(asset_id)
