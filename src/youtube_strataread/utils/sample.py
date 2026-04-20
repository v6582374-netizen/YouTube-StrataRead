"""Locate the bundled example outline (shipped under ``youtube_strataread/examples``)."""
from __future__ import annotations

from importlib import resources
from pathlib import Path


def sample_dir() -> Path:
    """Return the on-disk directory containing the shipped sample."""
    # ``importlib.resources.files`` resolves to a real path for editable /
    # wheel installs. ``sample`` is a subfolder of the ``examples`` package.
    return Path(str(resources.files("youtube_strataread.examples") / "sample"))


def sample_markdown() -> Path:
    d = sample_dir()
    mds = sorted(d.glob("*.md"))
    if not mds:
        raise FileNotFoundError(f"no markdown file found in sample dir: {d}")
    return mds[0]
