"""Single-shot pipeline.

Flow:
    URL → yt-dlp → raw.srt → plain text transcript → one LLM call
    (system = user's editable prompt, user = transcript) → <slug>.md

No chunking, no multi-step post-processing, no output validation. The only
instructions the model gets are exactly whatever the user's prompt file says.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from youtube_strataread.ai.base import get_provider
from youtube_strataread.ai.prompts import load_prompt
from youtube_strataread.config import resolve_provider_config
from youtube_strataread.downloader import cues_to_lines, download_subtitles, load_cues
from youtube_strataread.utils.logging import get_logger, stdout
from youtube_strataread.utils.text import short_hash, slugify

logger = get_logger()


@dataclass
class PipelineResult:
    video_id: str
    title: str
    slug: str
    out_dir: Path
    srt_path: Path
    markdown_path: Path


def run_pipeline(
    *,
    url: str,
    parent: Path,
    provider: str | None = None,
    model_override: str | None = None,
    lang: str | None = None,
    cookies_from_browser: str | None = None,
    cookiefile: Path | None = None,
    overwrite: bool = False,
    suffix: bool = False,
    prompt_path: Path | None = None,
) -> PipelineResult:
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)

    pc = resolve_provider_config(provider)
    if model_override:
        pc.model = model_override
    llm = get_provider(pc)

    stdout().print(f"[bold]provider[/] {pc.name} [dim](model={pc.model})[/]")
    stdout().print(f"[bold]parent[/] {parent}")
    if prompt_path is not None:
        stdout().print(f"[bold]prompt[/] {prompt_path}")

    # 1) download -------------------------------------------------------------
    stdout().print("[cyan]fetching subtitles...[/]")
    sub = download_subtitles(
        url,
        preferred_lang=lang,
        cookies_from_browser=cookies_from_browser,
        cookiefile=cookiefile,
    )
    slug = slugify(sub.title)
    out_dir = _resolve_out_dir(parent, slug, sub.video_id, overwrite=overwrite, suffix=suffix)
    srt_path = out_dir / "raw.srt"
    srt_path.write_text(sub.srt_text, encoding="utf-8")
    stdout().print(
        f"  saved {srt_path} [dim](lang={sub.language}, auto={sub.is_auto})[/]"
    )

    try:
        cues = load_cues(sub.srt_text)
        lines = cues_to_lines(cues)
        if not lines:
            raise RuntimeError("subtitle file was empty after cleanup")
        transcript = "\n".join(lines)

        system_prompt = load_prompt(prompt_path)

        progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold cyan]{task.description}[/]"),
            BarColumn(
                bar_width=32,
                complete_style="green",
                finished_style="green",
                pulse_style="magenta",
            ),
            TextColumn("[yellow]{task.fields[status]}[/]"),
            TextColumn("[dim]|[/]"),
            TimeElapsedColumn(),
            transient=False,
        )
        with progress:
            task = progress.add_task(
                "Analyzing transcript (translate · denoise · outline)...",
                total=None,
                status="thinking...",
            )
            received = {"n": 0}

            def _on_stream(chunk: str) -> None:
                received["n"] += len(chunk)
                progress.update(task, status=_status_text(received["n"]))

            def _on_status(status: str) -> None:
                progress.update(task, status=status)

            md = llm.chat(
                system=system_prompt,
                user=transcript,
                temperature=0.3,
                on_stream=_on_stream,
                on_status=_on_status,
            )
            progress.update(task, total=1, completed=1, status=_status_text(received["n"]))

        md = md.strip() + "\n"
        md_path = out_dir / f"{out_dir.name}.md"
        md_path.write_text(md, encoding="utf-8")
        return PipelineResult(
            video_id=sub.video_id,
            title=sub.title,
            slug=out_dir.name,
            out_dir=out_dir,
            srt_path=srt_path,
            markdown_path=md_path,
        )
    except Exception:
        crash = out_dir / f".by-crash-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.log"
        crash.write_text(traceback.format_exc(), encoding="utf-8")
        stdout().print(f"[red]pipeline failed; crash log: {crash}[/]")
        raise


def _resolve_out_dir(
    parent: Path,
    slug: str,
    video_id: str,
    *,
    overwrite: bool,
    suffix: bool,
) -> Path:
    target = parent / slug
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        return target
    if overwrite:
        return target
    if suffix:
        i = 2
        while True:
            candidate = parent / f"{slug}-{i}"
            if not candidate.exists():
                candidate.mkdir(parents=True)
                return candidate
            i += 1
    # default: append short hash based on video id for uniqueness
    candidate = parent / f"{slug}-{short_hash(video_id)}"
    if not candidate.exists():
        candidate.mkdir(parents=True)
        return candidate
    raise FileExistsError(
        f"output folder already exists: {target}. "
        f"Re-run with --overwrite or --suffix to decide."
    )


def _status_text(chars: int) -> str:
    return f"{chars:,} chars"
