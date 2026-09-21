"""Authenticated desktop boundary for the Minimalism module."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..minimalism.images import ImageService
from ..minimalism.store import ObjectLibrary, safe_file
from ..secrets import state_dir


class MinimalismRequest(BaseModel):
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)


def attach_minimalism(app: FastAPI, manager: Any):
    # Creating the module boundary never touches or migrates the source library.
    library = ObjectLibrary(
        Path(os.environ.get("EDISON_MINIMALISM_WORKSPACE", str(state_dir() / "minimalism"))),
        Path(os.environ["EDISON_MINIMALISM_SOURCE"])
        if "EDISON_MINIMALISM_SOURCE" in os.environ
        else None,
        Path(os.environ["EDISON_MINIMALISM_PREFERENCES"])
        if "EDISON_MINIMALISM_PREFERENCES" in os.environ
        else None,
    )
    images = ImageService(manager.secrets)
    app.state.minimalism = library
    app.state.minimalism_images = images

    @app.post("/v1/minimalism/capability")
    def capability(request: MinimalismRequest):
        action, args = request.capability, request.arguments
        try:
            if action == "library.snapshot":
                result = library.snapshot()
                result["image_ready"] = images.settings()["ready"]
            elif action == "migration.status":
                result = dict(library.progress)
            elif action == "image.settings":
                result = images.settings()
            elif action == "image.settings.save":
                result = images.save(args)
            elif action == "image.get":
                result = library.image(args["path"])
            elif action == "cover.generate":
                result = images.generate(library, args["id"])
            elif action == "backup.restore_directory":
                result = library.restore_directory(args["path"])
            elif action == "backup.export_directory":
                result = library.export_directory(args["path"])
            elif action == "cover.discard":
                library.initialize()
                with library.lock:
                    safe_file(library.active / "Pending", args["preview"]).unlink(missing_ok=True)
                result = {}
            else:
                result = library.mutate(action, args)
            return {"ok": True, "result": result}
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        except (OSError, KeyError, TypeError, zipfile.BadZipFile):
            return {"ok": False, "error": "资料操作未完成，请检查文件后重试。"}

    @app.get("/v1/minimalism/backup")
    def backup():
        try:
            return Response(
                library.export(),
                media_type="application/zip",
                headers={"Content-Disposition": 'attachment; filename="Minimalism.zip"'},
            )
        except (ValueError, OSError):
            return JSONResponse({"error": "备份未完成，请重试。"}, status_code=400)

    @app.post("/v1/minimalism/restore")
    async def restore(request: Request):
        # A zip of the upstream directory-package layout; no arbitrary server path input.
        import asyncio

        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 512 * 1024**2:
                return JSONResponse({"error": "备份文件不能超过 512 MB。"}, status_code=413)
        try:
            result = await asyncio.to_thread(library.restore, bytes(data))
            result["image_ready"] = images.settings()["ready"]
            return {"ok": True, "result": result}
        except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile):
            return JSONResponse(
                {"error": "备份无效或图片不完整，当前资料未替换。"}, status_code=400
            )
