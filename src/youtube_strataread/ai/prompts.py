"""Single user-editable prompt for the one-shot pipeline.

The entire 3-step reasoning now lives inside one system prompt that the user
(you) wrote. We hand that prompt + the raw subtitle transcript to the LLM in a
single call and trust the model to produce the final Markdown in one pass.

On first run the default is materialised to::

    <config_dir>/youtube-strataread/prompts/prompts.md

Edit that file in any text editor; the next ``by process`` / ``by run`` picks
it up automatically. ``BY_PROMPTS_DIR`` overrides the location.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from platformdirs import user_config_dir

from youtube_strataread.config import APP_NAME

PROMPT_FILENAME = "prompts.md"

# ---------------------------------------------------------------------------
# IMPORTANT: this string is the author's prompt kept verbatim. Do NOT rewrite
# it. Any edits must be made by the user either here or in prompts.md.
# ---------------------------------------------------------------------------
DEFAULT_PROMPT = """针对这份字幕文件，按照如下的思路处理。

第一步：
如果字幕文件是简体中文之外的任何语言，则需要先将其翻译成中文。如果本身就是简体中文，则忽略这一步。
第二步：
进行基本的信息冗余处理，比如语气词或者是其余车轱辘话（明确毫无价值的话）。然后得到一份干净的原始字幕文本（讲话人：讲话内容）。这一步得出的结果将作下一层的基础文本。
注意：这一步不能通过编写脚本的方式处理文本，而应该是基于分析的。
第三步：
针对第二步提供的文本，进行细致入微的分析和思考，然后做初步的内容划分，形成高屋建瓴的一级标题。
以此类推，向下展开标题，直到最终的“原子模块”。所谓原子模块指的是该模块非常紧密的围绕一个特定的主题，且没有必要进行进一步的拆分的最小模块。
注意：不要对第一层得到的基础文本做任何主观的修改或者分点，只能插入标题（或者说指作拆分的工作）。

要求：
1. 每个模块都必须是基于时间序列的（但是不要在最终的输出中标注时间点），不能擅作主张将前后看似相关的内容拼接起来（尽管他们确实属于一个主题）。
2. 如果发现分析的时候，某部分的文本理应整理成一个陈述句而非问句，比如“自托管推理与第三方模型推理”，这说明这部分文本需要进一步拆分。因为当不同主题的内容和逻辑被混杂在一起，就很难用一个问句来涵盖。
4. 一级标题一定要以问句的形式呈现（调动读者思维积极性，强制思考）。再往下的层级不强制使用问句形式，而是自主分析，哪种形式更合适就用哪种形式。

输出：一份骨架丰满且形式优雅的 md 文件，只包含正文内容，不要写入任何说明性的文字。
"""

README_TEXT = """# YouTube StrataRead 可编辑 Prompt

本目录下的 `prompts.md` 是 AI 流水线使用的**唯一** system prompt。
每次 `by process` / `by run` 都会重新读取该文件，修改立即生效，不需要重启或重装。

- `prompts.md` —— 会被当作 system 消息下发；字幕文本作为 user 消息发送。
- 恢复默认：`by prompts reset`
- 自定义目录：`export BY_PROMPTS_DIR=/path/to/prompts`
"""


def prompts_dir() -> Path:
    override = os.environ.get("BY_PROMPTS_DIR")
    d = Path(override) if override else Path(user_config_dir(APP_NAME)) / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def prompt_path() -> Path:
    return prompts_dir() / PROMPT_FILENAME


def _ensure_defaults(force: bool = False) -> None:
    d = prompts_dir()
    readme = d / "README.md"
    if force or not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")
    p = prompt_path()
    if force or not p.exists():
        p.write_text(DEFAULT_PROMPT, encoding="utf-8")
    _migrate_legacy(d)


def _migrate_legacy(d: Path) -> None:
    """Rename the old 3-file layout (translate/clean/outline.md) out of the way.

    These files were materialised by earlier versions of YouTube StrataRead. Under
    the single-prompt mode they are no longer consulted; we rename them with a
    ``.legacy`` suffix so the user can still see whatever customisations they
    had.
    """
    for name in ("translate.md", "clean.md", "outline.md"):
        src = d / name
        if src.exists() and not src.is_dir():
            dst = src.with_suffix(src.suffix + ".legacy")
            with contextlib.suppress(OSError):
                src.rename(dst)


def load_prompt(path: Path | None = None) -> str:
    """Return the current prompt text.

    If ``path`` is supplied, read that specific file. Otherwise fall back to
    the default ``prompts.md``. Defaults are always materialised on first run.
    """
    _ensure_defaults(force=False)
    p = path if path is not None else prompt_path()
    try:
        text = p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        text = ""
    return text or DEFAULT_PROMPT


def reset_prompt() -> Path:
    _ensure_defaults(force=True)
    return prompts_dir()


def list_prompts() -> list[Path]:
    """Return every user-visible prompt file in the prompts directory.

    * Excludes ``README.md`` and anything ending in ``.legacy``.
    * Sorted alphabetically by filename.
    * The default ``prompts.md`` is always pinned at the top when it exists,
      so it behaves like the built-in option in interactive menus.
    """
    _ensure_defaults(force=False)
    d = prompts_dir()
    files: list[Path] = []
    for p in sorted(d.glob("*.md"), key=lambda x: x.name):
        if p.name == "README.md":
            continue
        files.append(p)
    default = d / PROMPT_FILENAME
    if default in files:
        files.remove(default)
        files.insert(0, default)
    return files


__all__ = [
    "DEFAULT_PROMPT",
    "PROMPT_FILENAME",
    "prompt_path",
    "prompts_dir",
    "load_prompt",
    "list_prompts",
    "reset_prompt",
]
