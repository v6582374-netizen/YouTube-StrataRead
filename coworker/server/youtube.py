"""Edison's YouTube module, hosted inside the existing authenticated server.

The library owns its durable assets; the host owns model selection and credentials.
No second model client, credential copy, or auxiliary server is introduced.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from youtube_strataread.ai.prompts import load_prompt
from youtube_strataread.workbench.connection import ConnectionService, GoogleOAuthGateway
from youtube_strataread.workbench.discovery import SubscriptionDiscovery, YouTubeAtomFeeds
from youtube_strataread.workbench.library import (
    AutomaticBatch,
    LibraryService,
    PreparationService,
    YtDlpCaptions,
)
from youtube_strataread.workbench.sidecar import handle_request
from youtube_strataread.workbench.vault import AutomicVault
from youtube_strataread.workbench.workspace import LocalWorkspace, workspace_root


class HostManuscripts:
    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def generate(self, transcript: str) -> str:
        try:
            turn = self.manager.provider_complete(
                self.manager.model,
                [
                    {"role": "system", "content": load_prompt()},
                    {"role": "user", "content": transcript},
                ],
                tools=None,
            )
        except Exception as error:
            # Provider errors may contain request internals or credentials.
            raise RuntimeError("模型生成失败，请检查 Edison 的模型设置后重试。") from error
        if not turn.text or turn.tool_calls:
            raise RuntimeError("模型没有返回完整稿件，请重试或在 Edison 设置中切换模型。")
        return str(turn.text)


class YouTubeWorkbench:
    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.workspace = LocalWorkspace.open(workspace_root())
        self.connection = ConnectionService(
            workspace=self.workspace, vault=AutomicVault(), oauth=GoogleOAuthGateway()
        )
        self.discovery = SubscriptionDiscovery(workspace=self.workspace, feeds=YouTubeAtomFeeds())
        self.preparation = PreparationService(
            workspace=self.workspace, captions=YtDlpCaptions(), manuscripts=HostManuscripts(manager)
        )
        self.library = LibraryService(workspace=self.workspace, preparation=self.preparation)
        self.batch = AutomaticBatch(preparation=self.preparation)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="edison-youtube", daemon=True)
        self.discovery_lock = threading.Lock()
        self.discovery_error: str | None = None
        self.thread.start()

    def _run(self) -> None:
        next_discovery = 0.0
        while not self.stop.wait(1):
            if time.monotonic() >= next_discovery:
                next_discovery = time.monotonic() + 15 * 60
                try:
                    with self.discovery_lock:
                        self.discovery.refresh()
                    self.discovery_error = None
                except Exception:
                    self.discovery_error = "暂时无法刷新订阅，稍后自动重试。"
                if self.stop.is_set():
                    break
                self.batch.reset()
            try:
                # Keep assets queued until the host has a usable provider. A missing
                # model is configuration, not a hundred independent asset failures.
                self.prepare_one()
            except Exception:
                self.discovery_error = "批处理暂时不可用，请检查资料库后重试。"

    def prepare_one(self) -> bool:
        if not self.manager.get_settings().get("model_ready"):
            return False
        return self.batch.run_one()

    def close(self) -> None:
        self.preparation.stop()
        self.stop.set()
        self.thread.join(timeout=1)

    def dispatch(self, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if capability == "documents.open":
            try:
                document = self.library.document(str(arguments.get("video_id", "")))
                if sys.platform != "darwin":
                    raise ValueError("默认应用交接仅支持 macOS。")
                subprocess.run(["/usr/bin/open", str(document["path"])], check=True, timeout=10)
                return {"ok": True, "result": {"opened": True}}
            except (KeyError, ValueError, subprocess.SubprocessError, OSError):
                return {"ok": False, "error": "无法打开稿件，请确认该资料已有可用版本。"}
        if capability.startswith("collection."):
            with self.discovery_lock:
                response = handle_request(
                    {"capability": capability, "arguments": arguments},
                    self.workspace,
                    self.connection,
                    self.discovery,
                    self.library,
                )
        else:
            response = handle_request(
                {"capability": capability, "arguments": arguments},
                self.workspace,
                self.connection,
                self.discovery,
                self.library,
            )
        if response.get("ok") and capability == "activity.snapshot":
            response["result"].update(
                {
                    "model": self.manager.model,
                    "model_ready": bool(self.manager.get_settings().get("model_ready")),
                    "discovery_error": self.discovery_error,
                }
            )
        return response


class CapabilityRequest(BaseModel):
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)


def attach_youtube(app: FastAPI, manager: Any) -> None:
    app.state.youtube = None
    creation_lock = threading.Lock()

    @app.post("/v1/youtube/capability")
    def capability(request: CapabilityRequest) -> dict[str, Any]:
        with creation_lock:
            if app.state.youtube is None:
                app.state.youtube = YouTubeWorkbench(manager)
        return app.state.youtube.dispatch(request.capability, request.arguments)
