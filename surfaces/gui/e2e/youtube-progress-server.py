"""Isolated Edison host; only YouTube feeds/captions and paid model I/O are replaced."""

# ruff: noqa: E402 -- the isolated environment must precede host imports.
import json
import os
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace

root = Path(sys.argv[1])
shorts_mode = len(sys.argv) > 2 and sys.argv[2] == "shorts"
rate_mode = len(sys.argv) > 2 and sys.argv[2] == "rate"
os.environ.update(
    COWORKER_STATE_DIR=str(root / "host"),
    COWORKER_API_TOKEN="youtube-progress-e2e",
    YOUTUBE_WORKBENCH_WORKSPACE=str(root / "youtube"),
)
sys.path.insert(0, str(Path.cwd() / "tests"))

import uvicorn
from shorts_fixture import RegularVideos, player_page
from translation_fixture import source_from_prompt

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app, youtube
from youtube_strataread.downloader.youtube import SubtitleResult, YouTubeError
from youtube_strataread.workbench import shorts
from youtube_strataread.workbench.connection import SubscriptionSource
from youtube_strataread.workbench.discovery import Candidate, SourcePage
from youtube_strataread.workbench.workspace import LocalWorkspace
from youtube_strataread.workbench import workspace as workspace_module
workspace_module.time = SimpleNamespace(time=lambda: 1789819200.0)


def wait_for(name):
    deadline = time.monotonic() + 45
    while not (root / name).exists():
        if time.monotonic() > deadline:
            raise TimeoutError("E2E gate timed out")
        time.sleep(0.05)


class Provider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        wait_for("model-release")
        return AssistantTurn(text=source_from_prompt(messages[-1]["content"]), finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


class Captions:
    def acquire(self, url):
        wait_for("captions-release")
        if shorts_mode or rate_mode:
            with (root / "caption-calls").open("a") as output:
                output.write(url.split("=")[-1] + "\n")
        if rate_mode and url.endswith("=one") and not (root / "rate-release").exists():
            raise YouTubeError("ERROR: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests")
        return SubtitleResult(
            video_id=url.split("=")[-1],
            title="Fixture",
            language="en",
            is_auto=False,
            srt_text="1\n00:00:00,000 --> 00:00:02,000\nThe full source is retained for reading.\n",
            duration_seconds=2538,
        )


videos = [
    Candidate(
        video_id=key,
        channel_id="channel",
        channel_title="设计与思考",
        title=title,
        url=f"https://www.youtube.com/watch?v={key}",
        published_at="2026-09-19T00:00:00Z",
        published_ts=1789776000.0,
    )
    for key, title in [("one", "建筑与时间"), ("two", "材料的语言"), ("three", "慢下来的设计")]
]
if shorts_mode:
    videos = [
        Candidate(key, "channel", "设计与思考", title,
                  f"https://www.youtube.com/watch?v={key}", "2026-09-19T00:00:00Z", 1789776000.0)
        for key, title in [
            ("shorts00001", "平台 Shorts"),
            ("normal00001", "两分钟横屏讲解"),
            ("unknown0001", "暂时无法确认的视频"),
            ("saved000001", "已有的 Shorts 文稿"),
        ]
    ]
workspace = LocalWorkspace.open(root / "youtube")
if workspace.meta("fixture_seeded") != "1":
    # A fresh workspace starts with Auto Update off.
    workspace.set_meta("drain_paused", "1")
    workspace.replace_subscription_sources(
        [SubscriptionSource(channel_id="channel", title="设计与思考")]
    )
    for video in videos:
        workspace.add_candidate(video)
    if shorts_mode:
        workspace.save_manuscript("saved000001", "# 已有文稿\n\n应当保留。",
                                  generator="fixture", transcript_characters=0)
        workspace.set_preparation_state("saved000001", "ready")
    workspace.set_meta("fixture_seeded", "1")


class Feeds:
    def __init__(self, *, workspace, connection):
        pass

    def fetch(self, source):
        return SourcePage(videos)


youtube.YtDlpCaptions = Captions
youtube.YouTubeUploadsAPI = Feeds
if shorts_mode:
    from io import BytesIO
    from urllib.parse import parse_qs, urlsplit

    class PageResponse(BytesIO):
        status = 200

        def __init__(self, url, payload):
            super().__init__(payload.encode())
            self.url = url

        def geturl(self):
            return self.url

    def youtube_page(request, timeout):
        key = parse_qs(urlsplit(request.full_url).query)["v"][0]
        with (root / "classification-calls").open("a") as output:
            output.write(key + "\n")
        payload = "<html>Temporarily unavailable</html>" if key == "unknown0001" else player_page(key, key == "shorts00001")
        return PageResponse(request.full_url, payload)

    shorts.urlopen = youtube_page
else:
    shorts.YouTubeShortsClassifier.classify = RegularVideos.classify
manager = SessionManager(data_dir=root / "host", provider=Provider(), model="fixture-model")
manager.get_settings = lambda: {"model_ready": True}
app = create_app(manager)
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(json.dumps({"port": sock.getsockname()[1]}), flush=True)
uvicorn.Server(uvicorn.Config(app, log_level="error")).run(sockets=[sock])
