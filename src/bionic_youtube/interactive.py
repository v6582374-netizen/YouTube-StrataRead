"""Interactive provider + model picker shown before AI pipelines run.

This replaces the previous ``config use <provider>`` default-provider concept
with a per-invocation selection: each time the user runs ``by process`` /
``by run`` (without an explicit ``--provider``), we render a numbered menu of
all *supported* providers and their most commonly used models. The user picks
a provider, then a model (or supplies a custom one), and the chosen pair is
then fed into the pipeline.

The menu falls back to defaults silently when stdin is not a TTY (so unit
tests and scripted usage still work).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from bionic_youtube.ai.prompts import list_prompts as _list_prompts
from bionic_youtube.ai.prompts import prompt_path as _default_prompt_path
from bionic_youtube.config import (
    DEFAULT_MODELS,
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    mask_key,
    resolve_key,
)

# Curated model catalog. The *first* entry in each list is treated as the
# default selection for that provider (matches ``DEFAULT_MODELS`` where
# possible). Users can always pick "custom..." to type any slug.
MODEL_CATALOG: dict[str, list[str]] = {
    "openai": [
        "o4-mini",
        "o3",
        "o3-mini",
        "gpt-5",
        "gpt-5-mini",
        "gpt-4o",
        "gpt-4o-mini",
    ],
    "anthropic": [
        "claude-sonnet-4-5-20250929",
        "claude-opus-4-5-20250929",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    ],
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ],
    "compat": [
        "gpt-4o-mini",
        "claude-sonnet-4-5",
        "deepseek-reasoner",
        "deepseek-chat",
        "anthropic/claude-sonnet-4.6",
    ],
}


@dataclass
class Selection:
    provider: str
    model: str
    prompt_path: Path


def pick(console: Console | None = None) -> Selection:
    """Run the interactive picker. Falls back to defaults on non-TTY stdin."""
    console = console or Console()

    # Non-interactive fallback: pick default provider + its default model.
    if not sys.stdin.isatty():
        provider = DEFAULT_PROVIDER
        return Selection(
            provider=provider,
            model=DEFAULT_MODELS[provider],
            prompt_path=_default_prompt_path(),
        )

    provider = _pick_provider(console)
    model = _pick_model(console, provider)
    prompt = _pick_prompt(console)
    return Selection(provider=provider, model=model, prompt_path=prompt)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------
def _pick_provider(console: Console) -> str:
    providers = list(SUPPORTED_PROVIDERS)
    default_idx = providers.index(DEFAULT_PROVIDER) if DEFAULT_PROVIDER in providers else 0

    table = Table(title="请选择 Provider", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Provider")
    table.add_column("默认模型")
    table.add_column("Key")
    for i, name in enumerate(providers, start=1):
        key = resolve_key(name)
        table.add_row(
            str(i) + (" *" if i - 1 == default_idx else "  "),
            name,
            DEFAULT_MODELS.get(name, "-"),
            mask_key(key),
        )
    console.print(table)
    console.print("[dim]* 标记的是默认选项。直接回车即选择默认。[/]")

    prompt = f"输入序号 (1-{len(providers)}) [回车=默认 {providers[default_idx]}]: "
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return providers[default_idx]
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(providers):
                return providers[idx]
        if raw in providers:
            return raw
        console.print("[red]无效输入，请重新选择。[/]")


def _pick_model(console: Console, provider: str) -> str:
    catalog = list(MODEL_CATALOG.get(provider, []))
    default_model = DEFAULT_MODELS.get(provider) or (catalog[0] if catalog else "")
    if default_model and default_model not in catalog:
        catalog.insert(0, default_model)
    if not catalog:
        return _prompt_custom_model(console, default_model)

    default_idx = catalog.index(default_model) if default_model in catalog else 0

    table = Table(
        title=f"请选择模型  [dim](Provider = {provider})[/]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", style="bold")
    table.add_column("Model")
    for i, m in enumerate(catalog, start=1):
        table.add_row(str(i) + (" *" if i - 1 == default_idx else "  "), m)
    custom_idx = len(catalog) + 1
    table.add_row(str(custom_idx) + "  ", "[italic]自定义...[/]")
    console.print(table)

    prompt = f"输入序号 (1-{custom_idx}) [回车=默认 {catalog[default_idx]}]: "
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return catalog[default_idx]
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(catalog):
                return catalog[idx]
            if idx == custom_idx - 1:
                return _prompt_custom_model(console, default_model)
        console.print("[red]无效输入，请重新选择。[/]")


def _pick_prompt(console: Console) -> Path:
    """Ask the user which prompt file to use.

    Lists every ``*.md`` in the prompts dir (except README / legacy backups);
    the default ``prompts.md`` is pinned first. Users drop new prompt files in
    the directory to have them appear here — no CLI step required.
    """
    files = _list_prompts()
    if not files:
        return _default_prompt_path()
    if len(files) == 1:
        # Only the default exists; no point asking.
        return files[0]

    default_idx = 0
    table = Table(title="请选择 Prompt", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold")
    table.add_column("文件名")
    table.add_column("预览（首非空行）")
    for i, f in enumerate(files, start=1):
        preview = "-"
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s:
                    preview = s[:60]
                    break
        except OSError:
            pass
        table.add_row(
            str(i) + (" *" if i - 1 == default_idx else "  "),
            f.stem,
            preview,
        )
    console.print(table)
    console.print(f"[dim]提示：在 {files[0].parent} 中新增 .md 文件即可添加更多 Prompt。[/]")
    prompt_msg = f"输入序号 (1-{len(files)}) [回车=默认 {files[default_idx].stem}]: "
    while True:
        raw = input(prompt_msg).strip()
        if raw == "":
            return files[default_idx]
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(files):
                return files[idx]
        console.print("[red]无效输入，请重新选择。[/]")


def _prompt_custom_model(console: Console, default_model: str) -> str:
    hint = f" [回车=默认 {default_model}]" if default_model else ""
    while True:
        raw = input(f"输入模型名{hint}: ").strip()
        if raw:
            return raw
        if default_model:
            return default_model
        console.print("[red]模型名不能为空。[/]")
