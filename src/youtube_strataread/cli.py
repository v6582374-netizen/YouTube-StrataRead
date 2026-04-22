"""Top-level ``by`` CLI built with typer."""
from __future__ import annotations

from pathlib import Path

import typer

from youtube_strataread import config as cfg
from youtube_strataread.utils.logging import configure, die, stdout

app = typer.Typer(
    name="by",
    help="YouTube StrataRead: fetch YouTube subtitles, outline with AI, read in Bionic style.",
    no_args_is_help=True,
    add_completion=False,
)

config_app = typer.Typer(help="Manage providers and API keys.", no_args_is_help=True)
app.add_typer(config_app, name="config")
compat_config_app = typer.Typer(help="Manage named compat relay profiles.", no_args_is_help=True)
config_app.add_typer(compat_config_app, name="compat")

prompts_app = typer.Typer(help="Manage the editable AI prompts.", no_args_is_help=True)
app.add_typer(prompts_app, name="prompts")


@app.callback()
def _root(
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    no_color: bool = typer.Option(False, "--no-color"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config.toml path."),
) -> None:
    configure(verbose=verbose, no_color=no_color)
    if config_path is not None:
        # monkey-patch to honor --config
        import youtube_strataread.config as _c

        _c.config_path = lambda: config_path  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# config sub-commands
# ---------------------------------------------------------------------------
@config_app.command("set")
def config_set(
    provider: str = typer.Argument(
        ...,
        help="openai | anthropic | gemini | compat | deepseek | minimax | glm",
    ),
    key: str = typer.Option(..., "--key", prompt=True, hide_input=True),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Required for 'compat'; optional override for other providers.",
    ),
    model: str | None = typer.Option(
        None, "--model", help="Override default model for this provider."
    ),
) -> None:
    """Save credentials (and optionally base_url / model) for a provider."""
    try:
        backend = cfg.set_key(provider, key)
        if base_url:
            cfg.set_base_url(provider, base_url)
        if model:
            cfg.set_model(provider, model)
    except ValueError as e:
        die(str(e))
    extras = []
    if base_url:
        extras.append(f"base_url={base_url}")
    if model:
        extras.append(f"model={model}")
    extra_str = f" [{', '.join(extras)}]" if extras else ""
    label = f"compat:{cfg.DEFAULT_COMPAT_PROFILE}" if provider == "compat" else provider
    stdout().print(
        f"[green]ok[/] saved key for [bold]{label}[/] via {backend}{extra_str}"
    )


@config_app.command("get")
def config_get(provider: str = typer.Argument(...)) -> None:
    try:
        pc = cfg.resolve_provider_config(provider)
    except ValueError as e:
        die(str(e))
    stdout().print(
        f"provider=[bold]{pc.label}[/] model={pc.model} base_url={pc.base_url or '-'} "
        f"key={cfg.mask_key(pc.api_key)}"
    )


@config_app.command("use")
def config_use(provider: str = typer.Argument(...)) -> None:
    """Set the default provider."""
    try:
        cfg.set_default_provider(provider)
    except ValueError as e:
        die(str(e))
    stdout().print(f"[green]ok[/] default provider = [bold]{provider}[/]")


@compat_config_app.command("set")
def compat_config_set(
    profile: str = typer.Argument(..., help="Compat profile name"),
    key: str = typer.Option(..., "--key", prompt=True, hide_input=True),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="OpenAI-compatible relay endpoint, usually ending in /v1.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override default model for this compat profile.",
    ),
) -> None:
    try:
        backend = cfg.set_compat_key(profile, key)
        if base_url:
            cfg.set_compat_base_url(profile, base_url)
        if model:
            cfg.set_compat_model(profile, model)
    except ValueError as e:
        die(str(e))
    extras = []
    if base_url:
        extras.append(f"base_url={base_url}")
    if model:
        extras.append(f"model={model}")
    extra_str = f" [{', '.join(extras)}]" if extras else ""
    stdout().print(
        f"[green]ok[/] saved key for [bold]compat:{profile}[/] via {backend}{extra_str}"
    )


@compat_config_app.command("get")
def compat_config_get(profile: str = typer.Argument(..., help="Compat profile name")) -> None:
    try:
        pc = cfg.resolve_provider_config("compat", compat_profile=profile)
    except ValueError as e:
        die(str(e))
    stdout().print(
        f"provider=[bold]{pc.label}[/] model={pc.model} base_url={pc.base_url or '-'} "
        f"key={cfg.mask_key(pc.api_key)}"
    )


@compat_config_app.command("list")
def compat_config_list() -> None:
    app_cfg = cfg.load()
    profiles = cfg.list_compat_profiles()
    stdout().print(f"default compat profile: [bold]{app_cfg.default_compat_profile}[/]")
    if not profiles:
        stdout().print("[dim]no compat profiles configured[/]")
        return
    for profile in profiles:
        pc = cfg.resolve_provider_config("compat", compat_profile=profile)
        marker = " *" if profile == app_cfg.default_compat_profile else ""
        stdout().print(
            f"  {profile}{marker}: model={pc.model} base_url={pc.base_url or '-'} "
            f"key={cfg.mask_key(pc.api_key)}"
        )


@compat_config_app.command("use")
def compat_config_use(profile: str = typer.Argument(..., help="Compat profile name")) -> None:
    try:
        cfg.set_default_compat_profile(profile)
    except ValueError as e:
        die(str(e))
    stdout().print(f"[green]ok[/] default compat profile = [bold]{profile}[/]")


# ---------------------------------------------------------------------------
# prompts sub-commands (single-prompt mode)
# ---------------------------------------------------------------------------
@prompts_app.command("path")
def prompts_path_cmd() -> None:
    """Print the path of the editable prompt file."""
    from youtube_strataread.ai.prompts import load_prompt, prompt_path

    load_prompt()  # ensure default is materialised
    stdout().print(str(prompt_path()))


@prompts_app.command("reset")
def prompts_reset_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Overwrite prompts.md with the baked-in default (your original prompt)."""
    from youtube_strataread.ai.prompts import prompt_path, reset_prompt

    target = prompt_path()
    if not yes:
        ok = input(f"将重置 {target} 为默认 prompt，确认？[y/N] ").strip().lower()
        if ok not in {"y", "yes"}:
            stdout().print("[dim]已取消。[/]")
            return
    reset_prompt()
    stdout().print(f"[green]ok[/] reset {target}")


@prompts_app.command("show")
def prompts_show_cmd() -> None:
    """Print the currently effective prompt."""
    from youtube_strataread.ai.prompts import load_prompt, prompt_path

    body = load_prompt()
    stdout().print(f"[bold]prompt path[/] {prompt_path()}")
    stdout().rule("prompt")
    stdout().print(body)


@config_app.command("show")
def config_show() -> None:
    c = cfg.load()
    stdout().print(f"config file: {c.path}")
    stdout().print(f"default provider: [bold]{c.default_provider}[/]")
    stdout().print(f"default compat profile: [bold]{c.default_compat_profile}[/]")
    for name in cfg.FIXED_PROVIDERS:
        pc = cfg.resolve_provider_config(name)
        stdout().print(
            f"  {pc.label}: model={pc.model} base_url={pc.base_url or '-'} "
            f"key={cfg.mask_key(pc.api_key)}"
        )
    compat_profiles = cfg.list_compat_profiles()
    if not compat_profiles:
        stdout().print("  compat: profiles=0")
        return
    stdout().print(f"  compat: profiles={len(compat_profiles)}")
    for profile in compat_profiles:
        pc = cfg.resolve_provider_config("compat", compat_profile=profile)
        marker = " *" if profile == c.default_compat_profile else ""
        stdout().print(
            f"    {pc.label}{marker}: model={pc.model} base_url={pc.base_url or '-'} "
            f"key={cfg.mask_key(pc.api_key)}"
        )


# ---------------------------------------------------------------------------
# example
# ---------------------------------------------------------------------------
@app.command("example")
def example_cmd(
    mode: str = typer.Option("manual", "--mode", help="manual | stream"),
    cpm: int | None = typer.Option(None, "--cpm"),
    show_path: bool = typer.Option(
        False, "--path", help="Just print where the bundled sample lives."
    ),
) -> None:
    """Open the built-in sample outline in the Bionic reader."""
    from youtube_strataread.reader.app import run_reader
    from youtube_strataread.utils.sample import sample_dir, sample_markdown

    if show_path:
        stdout().print(str(sample_dir()))
        return
    md = sample_markdown()
    stdout().print(f"[dim]Reading built-in sample:[/] {md}")
    try:
        run_reader(md_path=md, mode=mode, cpm=cpm)
    except KeyboardInterrupt:
        stdout().print("\n[dim]bye[/]")


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
@app.command("fetch")
def fetch_cmd(
    url: str = typer.Argument(..., help="YouTube video URL"),
    lang: str | None = typer.Option(None, "--lang", help="Preferred subtitle language code"),
    out: Path | None = typer.Option(None, "--out", help="Parent directory (default: cwd)"),
    cookies_from_browser: str | None = typer.Option(
        None,
        "--cookies-from-browser",
        help="Load YouTube cookies from a local browser, e.g. safari or chrome:Default",
    ),
    cookies: Path | None = typer.Option(
        None,
        "--cookies",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to a Netscape-format cookies.txt file for YouTube authentication",
    ),
) -> None:
    """Download raw SRT subtitles into <cwd>/<slug>/raw.srt."""
    from youtube_strataread.downloader import download_subtitles
    from youtube_strataread.downloader.youtube import YouTubeError
    from youtube_strataread.utils.text import slugify

    parent = out or Path.cwd()
    parent.mkdir(parents=True, exist_ok=True)
    try:
        result = download_subtitles(
            url,
            preferred_lang=lang,
            cookies_from_browser=cookies_from_browser,
            cookiefile=cookies,
        )
    except YouTubeError as e:
        die(str(e))
    slug = slugify(result.title)
    target_dir = _ensure_target_dir(parent / slug)
    srt_path = target_dir / "raw.srt"
    srt_path.write_text(result.srt_text, encoding="utf-8")
    stdout().print(
        f"[green]ok[/] {srt_path} (lang={result.language}, auto={result.is_auto})"
    )


# ---------------------------------------------------------------------------
# process
# ---------------------------------------------------------------------------
@app.command("process")
def process_cmd(
    url: str = typer.Argument(..., help="YouTube video URL"),
    provider: str | None = typer.Option(None, "--provider"),
    compat_profile: str | None = typer.Option(
        None,
        "--compat-profile",
        help="Named compat profile when using --provider compat.",
    ),
    model: str | None = typer.Option(None, "--model"),
    lang: str | None = typer.Option(None, "--lang", help="Preferred source subtitle language"),
    out: Path | None = typer.Option(None, "--out", help="Parent directory (default: cwd)"),
    cookies_from_browser: str | None = typer.Option(
        None,
        "--cookies-from-browser",
        help="Load YouTube cookies from a local browser, e.g. safari or chrome:Default",
    ),
    cookies: Path | None = typer.Option(
        None,
        "--cookies",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to a Netscape-format cookies.txt file for YouTube authentication",
    ),
    overwrite: bool = typer.Option(False, "--overwrite"),
    suffix: bool = typer.Option(False, "--suffix", help="On slug collision, append -2, -3, ..."),
) -> None:
    """Fetch SRT and run the 3-step AI pipeline; produces <cwd>/<slug>/{raw.srt,<slug>.md}."""
    from youtube_strataread.interactive import pick as pick_provider
    from youtube_strataread.pipeline.orchestrator import run_pipeline

    if compat_profile and provider not in {None, "compat"}:
        die("--compat-profile only applies to --provider compat")

    prompt_path = None
    if provider is None:
        try:
            sel = pick_provider()
        except Exception as e:  # noqa: BLE001
            die(str(e))
        provider = sel.provider
        compat_profile = sel.compat_profile
        if model is None:
            model = sel.model
        prompt_path = sel.prompt_path

    parent = out or Path.cwd()
    try:
        result = run_pipeline(
            url=url,
            parent=parent,
            provider=provider,
            compat_profile=compat_profile,
            model_override=model,
            lang=lang,
            cookies_from_browser=cookies_from_browser,
            cookiefile=cookies,
            overwrite=overwrite,
            suffix=suffix,
            prompt_path=prompt_path,
        )
    except Exception as e:  # noqa: BLE001 - surface all errors to CLI
        die(str(e))
    stdout().print(f"[green]ok[/] {result.markdown_path}")


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------
@app.command("read")
def read_cmd(
    target: Path = typer.Argument(..., exists=True, help="Markdown file OR slug folder"),
    mode: str = typer.Option("manual", "--mode", help="manual | stream"),
    cpm: int | None = typer.Option(None, "--cpm", help="Characters-per-minute for stream mode"),
    wpm: int | None = typer.Option(None, "--wpm", help="Alias of --cpm for stream mode"),
) -> None:
    """Read a Markdown outline interactively."""
    from youtube_strataread.reader.app import run_reader

    md_path = _resolve_md(target)
    speed = cpm or wpm
    try:
        run_reader(md_path=md_path, mode=mode, cpm=speed)
    except KeyboardInterrupt:
        stdout().print("\n[dim]bye[/]")


# ---------------------------------------------------------------------------
# run (process + read)
# ---------------------------------------------------------------------------
@app.command("run")
def run_cmd(
    url: str = typer.Argument(...),
    mode: str = typer.Option("manual", "--mode"),
    provider: str | None = typer.Option(None, "--provider"),
    compat_profile: str | None = typer.Option(
        None,
        "--compat-profile",
        help="Named compat profile when using --provider compat.",
    ),
    model: str | None = typer.Option(None, "--model"),
    lang: str | None = typer.Option(None, "--lang"),
    out: Path | None = typer.Option(None, "--out"),
    cpm: int | None = typer.Option(None, "--cpm"),
    cookies_from_browser: str | None = typer.Option(
        None,
        "--cookies-from-browser",
        help="Load YouTube cookies from a local browser, e.g. safari or chrome:Default",
    ),
    cookies: Path | None = typer.Option(
        None,
        "--cookies",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to a Netscape-format cookies.txt file for YouTube authentication",
    ),
) -> None:
    """process + read in one shot."""
    from youtube_strataread.interactive import pick as pick_provider
    from youtube_strataread.pipeline.orchestrator import run_pipeline
    from youtube_strataread.reader.app import run_reader

    if compat_profile and provider not in {None, "compat"}:
        die("--compat-profile only applies to --provider compat")

    prompt_path = None
    if provider is None:
        try:
            sel = pick_provider()
        except Exception as e:  # noqa: BLE001
            die(str(e))
        provider = sel.provider
        compat_profile = sel.compat_profile
        if model is None:
            model = sel.model
        prompt_path = sel.prompt_path

    parent = out or Path.cwd()
    result = run_pipeline(
        url=url,
        parent=parent,
        provider=provider,
        compat_profile=compat_profile,
        model_override=model,
        lang=lang,
        cookies_from_browser=cookies_from_browser,
        cookiefile=cookies,
        overwrite=False,
        suffix=True,
        prompt_path=prompt_path,
    )
    stdout().print(f"[green]ok[/] generated {result.markdown_path}")
    try:
        run_reader(md_path=result.markdown_path, mode=mode, cpm=cpm)
    except KeyboardInterrupt:
        stdout().print("\n[dim]bye[/]")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ensure_target_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_md(target: Path) -> Path:
    if target.is_dir():
        mds = sorted(target.glob("*.md"))
        if not mds:
            die(f"no .md file found in folder {target}")
        return mds[0]
    return target


if __name__ == "__main__":
    app()
