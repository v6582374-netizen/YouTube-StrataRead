"""Library, document, and one-at-a-time preparation capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from youtube_strataread.ai.base import get_provider
from youtube_strataread.ai.prompts import load_prompt
from youtube_strataread.config import resolve_provider_config
from youtube_strataread.downloader import cues_to_lines, download_subtitles, load_cues
from youtube_strataread.downloader.youtube import SubtitleResult, YouTubeError
from youtube_strataread.workbench.workspace import LocalWorkspace


class CaptionAcquirer(Protocol):
    def acquire(self, url: str) -> SubtitleResult: ...


class ManuscriptGenerator(Protocol):
    def generate(self, transcript: str) -> str: ...


class YtDlpCaptions:
    def acquire(self, url: str) -> SubtitleResult:
        return download_subtitles(url)


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

    def request_drain_pause(self) -> dict[str, object]:
        self.workspace.set_meta("drain_paused", "1")
        return self.workspace.activity()

    def resume(self) -> dict[str, object]:
        self.workspace.set_meta("drain_paused", "0")
        return self.workspace.activity()

    def run_next(self) -> bool:
        if self.workspace.meta("drain_paused") == "1":
            return False
        asset = self.workspace.next_queued_asset()
        if asset is None:
            return False
        video_id = str(asset["video_id"])
        try:
            self.workspace.set_preparation_state(video_id, "acquiring")
            subtitles = self.captions.acquire(str(asset["url"]))
            self.workspace.store_transcript(
                video_id, language=subtitles.language, srt_text=subtitles.srt_text
            )
            transcript = "\n".join(cues_to_lines(load_cues(subtitles.srt_text))).strip()
            if not transcript:
                raise YouTubeError("subtitle was empty after cleanup")
        except YouTubeError as error:
            self.workspace.set_preparation_state(video_id, "unavailable", str(error))
            return True
        except Exception as error:  # acquisition may have safe adapter errors
            self.workspace.set_preparation_state(video_id, "failed", _safe_error(error))
            return True
        try:
            self.workspace.set_preparation_state(video_id, "generating")
            markdown = self.manuscripts.generate(transcript).strip()
            if not markdown:
                raise RuntimeError("manuscript generator returned no Markdown")
            self.workspace.save_manuscript(
                video_id,
                markdown,
                generator=type(self.manuscripts).__name__,
                transcript_characters=len(transcript),
            )
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
