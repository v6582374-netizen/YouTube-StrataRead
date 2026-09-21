"""Edison's YouTube module, hosted inside the existing authenticated server.

The library owns its durable assets; the host owns model selection and credentials.
No second model client, credential copy, or auxiliary server is introduced.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from youtube_strataread.workbench.connection import (
    ConnectionError,
    ConnectionService,
    GoogleOAuthGateway,
)
from youtube_strataread.workbench.discovery import SubscriptionDiscovery, YouTubeAtomFeeds
from youtube_strataread.workbench.library import (
    AutomaticBatch,
    LibraryService,
    PreparationService,
    YtDlpCaptions,
)
from youtube_strataread.workbench.sidecar import handle_request
from youtube_strataread.workbench.translation import (
    DEFAULTS,
    REQUIRED,
    TranslationPipeline,
    TranslationResult,
    settings,
    validate_settings,
)
from youtube_strataread.workbench.vault import AutomicVault
from youtube_strataread.workbench.workspace import LocalWorkspace, workspace_root


class HostManuscripts:
    def __init__(self, manager: Any, workspace: LocalWorkspace | None = None) -> None:
        self.manager = manager
        self.workspace = workspace

    def generate(self, transcript: str) -> str:
        return self.generate_result(transcript).markdown

    def generate_result(
        self,
        transcript: str,
        video_id: str | None = None,
        *,
        source_language: str = "auto-detected source language",
    ) -> TranslationResult:
        checkpoint = (
            self.workspace.translation_checkpoint(video_id) if self.workspace and video_id else None
        )
        return TranslationPipeline(
            self.manager.provider_complete,
            self.manager.model,
            settings(self.workspace),
            checkpoint,
            on_progress=(lambda stage, detail: self.workspace.report_stage(video_id, stage, detail))
            if self.workspace and video_id else None,
            on_console=(lambda message: self.workspace.report_console(video_id, message))
            if self.workspace and video_id else None,
        ).run(transcript, source_lang=source_language)


class YouTubeWorkbench:
    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.workspace = LocalWorkspace.open(workspace_root())
        self.workspace.recover_interrupted_preparations()
        self.connection = ConnectionService(
            workspace=self.workspace, vault=AutomicVault(), oauth=GoogleOAuthGateway()
        )
        self.discovery = SubscriptionDiscovery(
            workspace=self.workspace, feeds=YouTubeAtomFeeds(requests=self.workspace.youtube_requests)
        )
        self.preparation = PreparationService(
            workspace=self.workspace,
            captions=YtDlpCaptions(),
            manuscripts=HostManuscripts(manager, self.workspace),
        )
        self.library = LibraryService(workspace=self.workspace, preparation=self.preparation)
        self.batch = AutomaticBatch(preparation=self.preparation)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="edison-youtube", daemon=True)
        self.discovery_lock = threading.Lock()
        self.discovery_error: str | None = None
        self.refresh_requested = threading.Event()
        self.heartbeat_at: float | None = None
        self.discovering = False
        self.thread.start()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat, name="edison-youtube-heartbeat", daemon=True
        )
        self.heartbeat_thread.start()

    def _heartbeat(self) -> None:
        # Service liveness is distinct from pipeline progress: a slow provider
        # may leave the current stage unchanged while this process is responsive.
        while not self.stop.is_set() and self.thread.is_alive():
            self.heartbeat_at = time.time()
            self.stop.wait(2)

    def _run(self) -> None:
        next_discovery = 0.0
        while not self.stop.wait(1):
            if time.monotonic() >= next_discovery or self.refresh_requested.is_set():
                self.refresh_requested.clear()
                next_discovery = time.monotonic() + 15 * 60
                try:
                    self.discovering = True
                    with self.discovery_lock:
                        self.discovery.refresh()
                    self.discovery_error = None
                except Exception:
                    self.discovery_error = "暂时无法刷新订阅，稍后自动重试。"
                finally:
                    self.discovering = False
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
        self.heartbeat_thread.join(timeout=1)

    def dispatch(self, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if capability == "connection.refresh_subscriptions":
            try:
                result = self.connection.refresh_subscription_sources().as_result()
                self.refresh_requested.set()
                return {"ok": True, "result": result}
            except ConnectionError as error:
                return {"ok": False, "error": str(error)}
        if capability in {"collection.preferences", "collection.set_exclusions"}:
            if capability == "collection.set_exclusions":
                channels = arguments.get("excluded_channels")
                if (
                    not isinstance(channels, list)
                    or len(channels) > 10000
                    or any(
                        not isinstance(c, str) or not c.strip() or len(c) > 256 for c in channels
                    )
                ):
                    return {"ok": False, "error": "频道设置格式无效。"}
                self.workspace.set_excluded_channels(channels)
            return {
                "ok": True,
                "result": {
                    "sources": self.workspace.subscription_sources(),
                    "excluded_channels": self.workspace.excluded_channels(),
                },
            }
        if capability in {
            "translation.settings",
            "translation.set_settings",
            "generation.prompt",
            "generation.set_prompt",
        }:
            try:
                config = settings(self.workspace)
                if capability == "translation.set_settings":
                    config = validate_settings(arguments.get("settings"))
                    self.workspace.set_meta(
                        "youtube_translation", json.dumps(config, ensure_ascii=False)
                    )
                elif capability == "generation.set_prompt":
                    # Compatibility endpoint writes the same composition configuration.
                    prompt = arguments.get("prompt")
                    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 64000:
                        raise ValueError("请输入 1–64000 字的生成规则。")
                    config["prompts"]["composition"]["system"] = prompt.replace("{", "{{").replace(
                        "}", "}}"
                    )
                    config = validate_settings(config)
                    self.workspace.set_meta(
                        "youtube_translation", json.dumps(config, ensure_ascii=False)
                    )
                if capability.startswith("generation."):
                    return {
                        "ok": True,
                        "result": {
                            "prompt": config["prompts"]["composition"]["system"],
                            "default_prompt": DEFAULTS["prompts"]["composition"]["system"],
                        },
                    }
                return {
                    "ok": True,
                    "result": {
                        "settings": config,
                        "defaults": DEFAULTS,
                        "required": {
                            stage: {role: sorted(names) for role, names in pair.items()}
                            for stage, pair in REQUIRED.items()
                        },
                        "legacy_settings": self.workspace.meta("youtube_translation_v1_archive"),
                    },
                }
            except ValueError as error:
                return {"ok": False, "error": str(error)}
            except TypeError:
                return {"ok": False, "error": "翻译设置格式无效。"}
        if capability == "sources.open":
            try:
                asset = self.workspace.asset(str(arguments.get("video_id", "")))
                video_id = str(asset["video_id"])
                if sys.platform != "darwin" or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                    raise ValueError("Unsupported source")
                # Build from the retained identity, never a renderer-supplied URL.
                subprocess.run(
                    ["/usr/bin/open", f"https://www.youtube.com/watch?v={video_id}"],
                    check=True,
                    timeout=10,
                )
                return {"ok": True, "result": {"opened": True}}
            except (KeyError, ValueError, subprocess.SubprocessError, OSError):
                return {"ok": False, "error": "无法打开原始视频，请检查默认浏览器后重试。"}
        if capability in {"documents.open", "documents.open_translation"}:
            try:
                document = self.library.document(str(arguments.get("video_id", "")))
                if sys.platform != "darwin":
                    raise ValueError("默认应用交接仅支持 macOS。")
                path = (
                    document.get("translation_path")
                    if capability == "documents.open_translation"
                    else document["path"]
                )
                if not path:
                    raise ValueError("该版本没有单独的完整译文。")
                subprocess.run(["/usr/bin/open", str(path)], check=True, timeout=10)
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
        if response.get("ok") and capability == "connection.authorize":
            self.refresh_requested.set()
        if response.get("ok") and capability == "activity.snapshot":
            response["result"].update(
                {
                    "runtime": {
                        "heartbeat_at": self.heartbeat_at,
                        "worker_alive": self.thread.is_alive(),
                        "discovering": self.discovering,
                    },
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
