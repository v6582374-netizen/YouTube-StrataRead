"""YouTube subtitle fetcher backed by yt-dlp.

Given a URL we:
1. query video info (title, id, available subtitle languages)
2. pick the best subtitle (preferred lang -> official -> auto-generated)
3. download the SRT bytes and return them in-memory plus metadata
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_URL_PATTERNS = [
    re.compile(r"^https?://(?:www\.)?youtube\.com/watch\?[^#]*v=[\w-]+"),
    re.compile(r"^https?://youtu\.be/[\w-]+"),
    re.compile(r"^https?://(?:www\.)?youtube\.com/shorts/[\w-]+"),
    re.compile(r"^https?://(?:www\.)?youtube\.com/live/[\w-]+"),
]

_PREFERRED_LANGS_OFFICIAL = ["zh-Hans", "zh-CN", "zh", "en", "en-US", "en-GB"]
# Auto-generated captions: prefer the original source (usually English).
# YouTube tends to rate-limit translated auto-captions (e.g. zh-Hans),
# so we grab the source and let Step1 translate locally.
_PREFERRED_LANGS_AUTO = ["en", "en-US", "en-GB", "zh-Hans", "zh-CN", "zh"]


class YouTubeError(RuntimeError):
    """Raised when yt-dlp fails in an unrecoverable way."""


@dataclass
class SubtitleResult:
    video_id: str
    title: str
    language: str
    is_auto: bool
    srt_text: str


def validate_url(url: str) -> None:
    if not any(p.match(url) for p in _URL_PATTERNS):
        raise YouTubeError(
            "URL does not look like a YouTube video/shorts/live link: " + url
        )


def download_subtitles(url: str, preferred_lang: str | None = None) -> SubtitleResult:
    """Fetch the best-available SRT subtitle for ``url``.

    Strategy (to avoid 429 from trying non-existent languages):
        1. Probe video info (no download) to see which subtitles exist.
        2. Pick a single language per the preference order below.
        3. Re-invoke yt-dlp with just that one language.

    Preference order:
        1. ``preferred_lang`` (if supplied)
        2. simplified Chinese (``zh-Hans`` / ``zh-CN`` / ``zh``)
        3. English (``en`` / ``en-US`` / ``en-GB``)
        4. first official subtitle advertised
        5. any available auto-generated subtitle
    """
    validate_url(url)

    from yt_dlp import YoutubeDL  # imported lazily to speed up CLI startup
    from yt_dlp.utils import DownloadError

    # --- phase 1: probe ----------------------------------------------------
    probe_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "listsubtitles": False,
    }
    try:
        with YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise YouTubeError(str(e)) from e

    video_id = str(info.get("id"))
    title = str(info.get("title") or video_id)
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    lang, is_auto = _pick_language(subs, auto, preferred_lang)
    if lang is None:
        raise YouTubeError(
            "no subtitles (official or auto-generated) were available for this video"
        )

    # --- phase 2: download just that one language --------------------------
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        dl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": not is_auto,
            "writeautomaticsub": is_auto,
            "subtitlesformat": "srt",
            "subtitleslangs": [lang],
            "outtmpl": str(tmp / "%(id)s.%(ext)s"),
            "convertsubtitles": "srt",
        }
        try:
            with YoutubeDL(dl_opts) as ydl:
                ydl.extract_info(url, download=True)
        except DownloadError as e:
            raise YouTubeError(str(e)) from e

        srt_path = _locate_srt(tmp, video_id, lang)
        if srt_path is None:
            raise YouTubeError(
                f"yt-dlp reported subtitle language '{lang}' but the .srt file is missing"
            )
        srt_text = srt_path.read_text(encoding="utf-8")
        return SubtitleResult(
            video_id=video_id,
            title=title,
            language=lang,
            is_auto=is_auto,
            srt_text=srt_text,
        )


def _build_lang_pref(preferred: str | None, *, is_auto: bool = False) -> list[str]:
    base = _PREFERRED_LANGS_AUTO if is_auto else _PREFERRED_LANGS_OFFICIAL
    langs = list(base)
    if preferred:
        langs = [preferred, *[lc for lc in langs if lc != preferred]]
    return langs


def _pick_language(
    subs: dict[str, list[dict]],
    auto: dict[str, list[dict]],
    preferred: str | None,
) -> tuple[str | None, bool]:
    """Return (lang_code, is_auto)."""
    # Official subs first, with CJK-biased preference.
    for candidate in _build_lang_pref(preferred, is_auto=False):
        if candidate in subs:
            return candidate, False
    if subs:
        return next(iter(subs)), False
    # Fall back to auto-captions, biased toward the English *source*.
    for candidate in _build_lang_pref(preferred, is_auto=True):
        if candidate in auto:
            return candidate, True
    if auto:
        return next(iter(auto)), True
    return None, False


def _locate_srt(tmp: Path, video_id: str, lang: str) -> Path | None:
    direct = tmp / f"{video_id}.{lang}.srt"
    if direct.exists():
        return direct
    # fallback: any .srt that matches the language
    for p in tmp.glob(f"{video_id}.*.srt"):
        if f".{lang}." in p.name:
            return p
    # last resort: any srt file in the dir
    for p in tmp.glob("*.srt"):
        return p
    return None
