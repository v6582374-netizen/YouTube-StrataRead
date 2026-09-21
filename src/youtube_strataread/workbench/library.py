"""Library, document, and one-at-a-time preparation capabilities."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from youtube_strataread.ai.base import get_provider
from youtube_strataread.ai.prompts import load_prompt
from youtube_strataread.config import resolve_provider_config
from youtube_strataread.downloader import cues_to_lines, download_subtitles, load_cues
from youtube_strataread.downloader.request_policy import (
    YouTubeRequestPolicy,
    YouTubeRequestsStopped,
    rate_limit_error,
)
from youtube_strataread.downloader.youtube import SubtitleResult, YouTubeError
from youtube_strataread.workbench.shorts import ShortsClassifier, YouTubeShortsClassifier
from youtube_strataread.workbench.workspace import LocalWorkspace


class CaptionAcquirer(Protocol):
    def acquire(self, url: str) -> SubtitleResult: ...


class ManuscriptGenerator(Protocol):
    def generate(self, transcript: str) -> str: ...


class YtDlpCaptions:
    def __init__(self, requests: YouTubeRequestPolicy | None = None) -> None:
        self.requests = requests
        self.on_metadata: Callable[[str, float | None], None] | None = None

    def acquire(self, url: str) -> SubtitleResult:
        return download_subtitles(url, request_policy=self.requests, on_metadata=self.on_metadata)


class ConfiguredManuscripts:
    """Reuse the existing user-configured provider and faithful Chinese prompt."""

    def generate(self, transcript: str) -> str:
        provider = get_provider(resolve_provider_config(None))
        return provider.chat(system=load_prompt(), user=transcript, temperature=0.3)


@dataclass
class PreparationService:
    workspace: LocalWorkspace
    captions: CaptionAcquirer
    manuscripts: ManuscriptGenerator
    shorts: ShortsClassifier = field(default_factory=YouTubeShortsClassifier)
    _claim_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _stopping: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.captions, YtDlpCaptions):
            self.captions.requests = self.workspace.youtube_requests
            self.captions.on_metadata = self.workspace.record_video_duration
        if isinstance(self.shorts, YouTubeShortsClassifier):
            self.shorts.requests = self.workspace.youtube_requests

    def stop(self) -> None:
        """Prevent new claims while allowing an already claimed asset to finish."""
        with self._claim_lock:
            self._stopping = True
            self.workspace.youtube_requests.stopped.set()

    def _defer_request(self, video_id: str, error: Exception) -> bool:
        if isinstance(error, YouTubeRequestsStopped):
            self.workspace.set_preparation_state(video_id, "queued")
            return True
        limited = rate_limit_error(error)
        if limited is None:
            return False
        self.workspace.youtube_requests.limit(limited)
        self.workspace.defer_rate_limited(video_id, attempted=limited.response_received)
        return True

    def request_drain_pause(self) -> dict[str, object]:
        self.workspace.set_meta("drain_paused", "1")
        return self.workspace.activity()

    def resume(self) -> dict[str, object]:
        self.workspace.set_meta("drain_paused", "0")
        return self.workspace.activity()

    def run_next(self) -> bool:
        with self._claim_lock:
            if self._stopping:
                return False
            asset = self.workspace.claim_next_queued_asset()
        if asset is None:
            return False
        video_id = str(asset["video_id"])
        if asset["manuscript_version"] is None and asset["shorts_status"] != "video":
            try:
                is_short = self.shorts.classify(video_id)
                if type(is_short) is not bool:
                    is_short = None
            except Exception as error:
                if self._defer_request(video_id, error):
                    return True
                # An unavailable detector is uncertainty, never permission to generate.
                is_short = None
            self.workspace.record_shorts_classification(video_id, is_short)
            if is_short is not False:
                return True
        try:
            retained = self.workspace.retained_transcript(video_id)
            if retained:
                srt_text = retained["content"]
                source_language = retained["language"]
            else:
                subtitles = self.captions.acquire(str(asset["url"]))
                self.workspace.record_video_duration(video_id, subtitles.duration_seconds)
                srt_text = subtitles.srt_text
                source_language = subtitles.language
                self.workspace.store_transcript(
                    video_id, language=subtitles.language, srt_text=srt_text
                )
                self.workspace.youtube_requests.caption_succeeded()
            transcript = "\n".join(cues_to_lines(load_cues(srt_text))).strip()
            if not transcript:
                raise YouTubeError("subtitle was empty after cleanup")
        except YouTubeError as error:
            if self._defer_request(video_id, error):
                return True
            self.workspace.set_preparation_state(video_id, "unavailable", str(error))
            return True
        except Exception as error:  # acquisition may have safe adapter errors
            if self._defer_request(video_id, error):
                return True
            self.workspace.set_preparation_state(video_id, "failed", _safe_error(error))
            return True
        try:
            self.workspace.set_preparation_state(video_id, "generating")
            generate_result = getattr(self.manuscripts, "generate_result", None)
            result = (
                generate_result(transcript, video_id, source_language=source_language)
                if generate_result
                else None
            )
            markdown = (
                result.markdown if result else self.manuscripts.generate(transcript)
            ).strip()
            if not markdown:
                raise RuntimeError("manuscript generator returned no Markdown")
            self.workspace.save_manuscript(
                video_id,
                markdown,
                generator=type(self.manuscripts).__name__,
                transcript_characters=len(transcript),
                translation=result.translation if result else None,
                provenance=result.provenance if result else None,
            )
            self.workspace.translation_checkpoint(video_id).unlink(missing_ok=True)
            self.workspace.set_preparation_state(video_id, "ready")
        except Exception as error:
            self.workspace.set_preparation_state(video_id, "failed", _safe_error(error))
        return True


@dataclass
class AutomaticBatch:
    """A bounded serial batch; its state is also the activity-center progress."""

    preparation: PreparationService
    limit: int = 100
    completed: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 100:
            raise ValueError("batch limit must be between 1 and 100")
        self._publish()

    def reset(self) -> None:
        self.completed = 0
        self._publish()

    def run_one(self) -> bool:
        if self.completed >= self.limit or not self.preparation.run_next():
            return False
        self.completed += 1
        self._publish()
        return True

    def _publish(self) -> None:
        self.preparation.workspace.set_batch_progress(limit=self.limit, completed=self.completed)


@dataclass
class LibraryService:
    workspace: LocalWorkspace
    preparation: PreparationService

    def list_assets(self, **filters: object) -> dict[str, object]:
        assets = self.workspace.assets(**filters)  # type: ignore[arg-type]
        return {"assets": assets, "total": len(assets)}

    def inspect(self, video_id: str) -> dict[str, object]:
        asset = self.workspace.asset(video_id)
        return {
            **asset,
            "generation_records": self.workspace.generation_records(video_id),
            "source_trace": {
                "video_url": asset["url"],
                "transcript_available": bool(asset["transcript_path"]),
                "transcript_path": asset["transcript_path"],
                "translation_available": bool(
                    self.workspace.document(video_id).get("translation_path")
                )
                if asset["manuscript_version"]
                else False,
            },
        }

    def document(self, video_id: str) -> dict[str, object]:
        return self.workspace.document(video_id)

    def set_reading_state(self, video_id: str, state: str) -> dict[str, object]:
        self.workspace.set_reading_state(video_id, state)
        return self.inspect(video_id)

    def regenerate(self, video_id: str) -> dict[str, object]:
        self.workspace.queue_regeneration(video_id)
        return self.inspect(video_id)

    def delete(self, video_id: str) -> dict[str, object]:
        self.workspace.delete_asset(video_id)
        return {"deleted": video_id}

    def search(self, **filters: object) -> dict[str, object]:
        return self.list_assets(**filters)

    def activity(self) -> dict[str, object]:
        return self.workspace.activity()

    def retry(self, video_id: str) -> dict[str, object]:
        return {"queued": self.workspace.retry_failed(video_id)}

    def retry_all_failed(self) -> dict[str, object]:
        return {"queued": self.workspace.retry_failed()}

    def drain_pause(self) -> dict[str, object]:
        return self.preparation.request_drain_pause()

    def resume(self) -> dict[str, object]:
        return self.preparation.resume()


def _safe_error(error: Exception) -> str:
    return str(error).strip() or error.__class__.__name__
