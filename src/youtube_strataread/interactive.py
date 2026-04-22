"""Interactive provider + model picker shown before AI pipelines run."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from youtube_strataread.ai.prompts import list_prompts as _list_prompts
from youtube_strataread.ai.prompts import prompt_path as _default_prompt_path
from youtube_strataread.config import (
    DEFAULT_MODELS,
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    list_compat_profiles,
    mask_key,
    resolve_provider_config,
)
from youtube_strataread.config import (
    load as load_config,
)

# Curated model catalog. The *first* entry in each list is treated as the
# default selection for that provider when the user's own config does not
# override it. Users can always pick "custom..." to type any slug.
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
        "claude-opus-4-1",
        "deepseek-reasoner",
        "deepseek-chat",
    ],
    "deepseek": [
        "deepseek-reasoner",
        "deepseek-chat",
    ],
    "minimax": [
        "MiniMax-M2.7",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2.5",
        "MiniMax-M2.5-highspeed",
        "MiniMax-M2.1",
        "MiniMax-M2.1-highspeed",
    ],
    "glm": [
        "glm-5.1",
        "glm-5",
        "glm-4.7",
    ],
}


@dataclass
class Selection:
    provider: str
    model: str
    prompt_path: Path
    compat_profile: str | None = None


def pick(console: Console | None = None) -> Selection:
    """Run the interactive picker. Falls back to defaults on non-TTY stdin."""
    console = console or Console()
    default_provider = _current_default_provider()

    if not sys.stdin.isatty():
        pc = resolve_provider_config(default_provider)
        return Selection(
            provider=pc.name,
            model=pc.model,
            prompt_path=_default_prompt_path(),
            compat_profile=pc.profile_name,
        )

    provider = _pick_provider(console, default_provider)
    compat_profile = _pick_compat_profile(console) if provider == "compat" else None
    model = _pick_model(console, provider, compat_profile)
    prompt = _pick_prompt(console)
    return Selection(
        provider=provider,
        model=model,
        prompt_path=prompt,
        compat_profile=compat_profile,
    )


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------
def _pick_provider(console: Console, default_provider: str) -> str:
    providers = list(SUPPORTED_PROVIDERS)
    default_idx = providers.index(default_provider) if default_provider in providers else 0

    table = Table(title="请选择 Provider", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Provider")
    table.add_column("默认模型")
    table.add_column("Key")
    for i, name in enumerate(providers, start=1):
        pc = resolve_provider_config(name)
        provider_label = name
        if name == "compat":
            provider_label = f"{name} ({len(list_compat_profiles())} profiles)"
        table.add_row(
            str(i) + (" *" if i - 1 == default_idx else "  "),
            provider_label,
            pc.model or DEFAULT_MODELS.get(name, "-"),
            mask_key(pc.api_key),
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


def _pick_compat_profile(console: Console) -> str:
    profiles = list_compat_profiles()
    if not profiles:
        raise RuntimeError(
            "compat provider has no configured profiles. Run: "
            "by config compat set <name> --key <API_KEY> --base-url https://your-relay/v1"
        )
    if len(profiles) == 1:
        return profiles[0]

    cfg = load_config()
    default_profile = cfg.default_compat_profile
    default_idx = profiles.index(default_profile) if default_profile in profiles else 0

    table = Table(
        title="请选择 Compat Profile",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", style="bold")
    table.add_column("Profile")
    table.add_column("Model")
    table.add_column("Base URL")
    table.add_column("Key")
    for i, profile in enumerate(profiles, start=1):
        pc = resolve_provider_config("compat", compat_profile=profile)
        table.add_row(
            str(i) + (" *" if i - 1 == default_idx else "  "),
            profile,
            pc.model,
            pc.base_url or "-",
            mask_key(pc.api_key),
        )
    console.print(table)

    prompt = f"输入序号 (1-{len(profiles)}) [回车=默认 {profiles[default_idx]}]: "
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return profiles[default_idx]
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(profiles):
                return profiles[idx]
        if raw in profiles:
            return raw
        console.print("[red]无效输入，请重新选择。[/]")


def _pick_model(console: Console, provider: str, compat_profile: str | None) -> str:
    catalog = list(MODEL_CATALOG.get(provider, []))
    default_model = resolve_provider_config(
        provider,
        compat_profile=compat_profile,
    ).model
    if default_model and default_model not in catalog:
        catalog.insert(0, default_model)
    if not catalog:
        return _prompt_custom_model(console, default_model)

    default_idx = catalog.index(default_model) if default_model in catalog else 0

    title = f"请选择模型  [dim](Provider = {provider}"
    if compat_profile:
        title += f":{compat_profile}"
    title += ")[/]"

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Model")
    for i, model in enumerate(catalog, start=1):
        table.add_row(str(i) + (" *" if i - 1 == default_idx else "  "), model)
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
    """Ask the user which prompt file to use."""
    files = _list_prompts()
    if not files:
        return _default_prompt_path()
    if len(files) == 1:
        return files[0]

    default_idx = 0
    table = Table(title="请选择 Prompt", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold")
    table.add_column("文件名")
    table.add_column("预览（首非空行）")
    for i, file in enumerate(files, start=1):
        preview = "-"
        try:
            for line in file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped:
                    preview = stripped[:60]
                    break
        except OSError:
            pass
        table.add_row(
            str(i) + (" *" if i - 1 == default_idx else "  "),
            file.stem,
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


def _current_default_provider() -> str:
    provider = load_config().default_provider
    if provider in SUPPORTED_PROVIDERS:
        return provider
    return DEFAULT_PROVIDER
