from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from youtube_strataread.downloader.srt import load_cues
from youtube_strataread.downloader.youtube import YouTubeError, download_subtitles


def _install_fake_ytdlp(
    monkeypatch,
    *,
    info: dict,
    files_by_lang: dict[str, list[tuple[str, str]]],
    fail_on_probe: str | None = None,
    seen_opts: list[dict] | None = None,
) -> None:
    class FakeDownloadError(Exception):
        pass

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts
            if seen_opts is not None:
                seen_opts.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            if not download:
                if fail_on_probe is not None:
                    raise FakeDownloadError(fail_on_probe)
                return info
            tmp = Path(self.opts["outtmpl"]).parent
            lang = self.opts["subtitleslangs"][0]
            for filename, content in files_by_lang.get(lang, []):
                (tmp / filename).write_text(content, encoding="utf-8")
            return info

    yt_dlp_module = ModuleType("yt_dlp")
    yt_dlp_module.YoutubeDL = FakeYoutubeDL
    utils_module = ModuleType("yt_dlp.utils")
    utils_module.DownloadError = FakeDownloadError
    monkeypatch.setitem(sys.modules, "yt_dlp", yt_dlp_module)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", utils_module)


def test_download_subtitles_prefers_real_subtitles_over_live_chat(monkeypatch) -> None:
    info = {
        "id": "vid123",
        "title": "Demo",
        "subtitles": {"live_chat": [{}], "en": [{}]},
        "automatic_captions": {},
    }
    _install_fake_ytdlp(
        monkeypatch,
        info=info,
        files_by_lang={
            "en": [("vid123.en.srt", "1\n00:00:00,000 --> 00:00:01,000\nHello world\n")],
        },
    )

    result = download_subtitles("https://youtu.be/abcdefghijk")

    assert result.language == "en"
    assert result.is_auto is False
    assert "Hello world" in result.srt_text


def test_download_subtitles_falls_back_to_live_chat_and_synthesizes_srt(monkeypatch) -> None:
    info = {
        "id": "vid456",
        "title": "Chat only",
        "subtitles": {"live_chat": [{}]},
        "automatic_captions": {},
    }
    live_chat_payload = json.dumps(
        {
            "replayChatItemAction": {
                "videoOffsetTimeMsec": "1000",
                "actions": [
                    {
                        "addChatItemAction": {
                            "item": {
                                "liveChatTextMessageRenderer": {
                                    "authorName": {"simpleText": "Alice"},
                                    "message": {"runs": [{"text": "Hello "}, {"text": "world"}]},
                                }
                            }
                        }
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    _install_fake_ytdlp(
        monkeypatch,
        info=info,
        files_by_lang={
            "live_chat": [("vid456.live_chat.json", live_chat_payload + "\n")],
        },
    )

    result = download_subtitles("https://youtu.be/abcdefghijk")
    cues = load_cues(result.srt_text)

    assert result.language == "live_chat"
    assert result.is_auto is False
    assert cues
    assert cues[0].text == "Alice: Hello world"


def test_download_subtitles_errors_when_live_chat_has_no_readable_messages(monkeypatch) -> None:
    info = {
        "id": "vid789",
        "title": "Empty chat",
        "subtitles": {"live_chat": [{}]},
        "automatic_captions": {},
    }
    live_chat_payload = json.dumps(
        {
            "replayChatItemAction": {
                "videoOffsetTimeMsec": "1000",
                "actions": [
                    {
                        "addLiveChatTickerItemAction": {
                            "item": {
                                "liveChatTickerPaidMessageItemRenderer": {}
                            }
                        }
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    _install_fake_ytdlp(
        monkeypatch,
        info=info,
        files_by_lang={
            "live_chat": [("vid789.live_chat.json", live_chat_payload + "\n")],
        },
    )

    with pytest.raises(YouTubeError, match="did not contain any readable chat messages"):
        download_subtitles("https://youtu.be/abcdefghijk")


def test_download_subtitles_forwards_cookie_auth_to_ytdlp(monkeypatch, tmp_path) -> None:
    info = {
        "id": "vid999",
        "title": "Cookie video",
        "subtitles": {"en": [{}]},
        "automatic_captions": {},
    }
    seen_opts: list[dict] = []
    cookiefile = tmp_path / "cookies.txt"
    cookiefile.write_text("cookies", encoding="utf-8")
    _install_fake_ytdlp(
        monkeypatch,
        info=info,
        files_by_lang={
            "en": [("vid999.en.srt", "1\n00:00:00,000 --> 00:00:01,000\nHello world\n")],
        },
        seen_opts=seen_opts,
    )

    result = download_subtitles(
        "https://youtu.be/abcdefghijk",
        cookies_from_browser="firefox:Default",
        cookiefile=cookiefile,
    )

    assert result.language == "en"
    assert len(seen_opts) == 2
    for opts in seen_opts:
        assert opts["cookiefile"] == str(cookiefile)
        assert opts["cookiesfrombrowser"] == ("firefox", "Default", None, None)


def test_download_subtitles_surfaces_cookie_hint_on_bot_check(monkeypatch) -> None:
    _install_fake_ytdlp(
        monkeypatch,
        info={},
        files_by_lang={},
        fail_on_probe="ERROR: [youtube] abc123: Sign in to confirm you're not a bot.",
    )

    with pytest.raises(YouTubeError, match="--cookies-from-browser safari"):
        download_subtitles("https://youtu.be/abcdefghijk")
