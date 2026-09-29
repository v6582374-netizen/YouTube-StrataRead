"""The signed-in YouTube session a server presents when YouTube treats its address as a bot.

A replacement is proven against a real watch page before it is written, so a
broken paste never displaces a working session.
"""

from __future__ import annotations

import os
import re
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from youtube_strataread.downloader.youtube import youtube_cookie_file

_DOMAINS = re.compile(r"^\.?(?:[\w-]+\.)*(?:youtube\.com|google\.com)$")
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
_PLAYABILITY = re.compile(r'"playabilityStatus":\{"status":"([A-Z_]+)"(?:,"reason":"([^"]*)")?')
_MAX_COOKIES = 500


def open_page(request: Request, path: Path | None = None, timeout: float = 15):
    cookies = path or youtube_cookie_file()
    if cookies is None or not cookies.exists():
        return urlopen(request, timeout=timeout)
    jar = MozillaCookieJar(str(cookies))
    jar.load(ignore_discard=True, ignore_expires=True)
    return build_opener(HTTPCookieProcessor(jar)).open(request, timeout=timeout)


def to_cookie_file(text: str) -> str:
    """Accept a cookies.txt export or a copied ``Cookie:`` request header."""
    text = text.strip()
    rows: list[str] = []
    if "\t" in text:
        for line in text.splitlines():
            fields = line.split("\t")
            domain = fields[0].removeprefix("#HttpOnly_")
            if len(fields) == 7 and _DOMAINS.match(domain):
                rows.append(line.strip("\r"))
    else:
        header = re.sub(r"^\s*cookie\s*:\s*", "", text, flags=re.I)
        expires = str(int(time.time()) + 365 * 86400)
        for pair in header.split(";"):
            name, separator, value = pair.strip().partition("=")
            if separator and re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
                rows.append("\t".join([".youtube.com", "TRUE", "/", "TRUE", expires, name, value.strip()]))
    if not rows:
        raise ValueError("没有识别到 YouTube Cookie。请粘贴 cookies.txt 内容，或开发者工具中 youtube.com 请求的 Cookie 请求头。")
    if len(rows) > _MAX_COOKIES:
        raise ValueError("Cookie 数量过多，请只导出 youtube.com 的 Cookie。")
    return "# Netscape HTTP Cookie File\n" + "\n".join(rows) + "\n"


def verify(path: Path, video_id: str) -> dict[str, object]:
    """Signed in, and a recent watch page is served instead of a bot check."""
    request = Request(f"https://www.youtube.com/watch?v={video_id}&hl=en", headers=_HEADERS)
    try:
        with open_page(request, path) as response:
            page = response.read(4 * 1024 * 1024).decode("utf-8", "replace")
    except (OSError, ValueError) as error:
        return {"usable": False, "signed_in": False, "detail": f"无法访问 YouTube：{error}"}
    signed_in = '"LOGGED_IN":true' in page
    match = _PLAYABILITY.search(page)
    status, reason = (match.group(1), match.group(2) or "") if match else ("UNKNOWN", "")
    blocked = status == "LOGIN_REQUIRED"
    if not signed_in:
        detail = "YouTube 不认为这些 Cookie 处于登录状态，可能已退出或过期。"
    elif blocked:
        detail = f"已登录，但 YouTube 仍拦截访问：{reason or status}"
    else:
        detail = "可用：已登录，视频页面正常返回。"
    return {"usable": signed_in and not blocked, "signed_in": signed_in, "detail": detail,
            "video_id": video_id, "checked_at": time.time()}


def status(path: Path | None) -> dict[str, object]:
    if path is None:
        return {"enabled": False}
    if not path.exists():
        return {"enabled": True, "present": False}
    count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.count("\t") == 6)
    return {"enabled": True, "present": True, "cookie_count": count, "updated_at": path.stat().st_mtime}


def replace(path: Path, text: str, video_id: str) -> dict[str, object]:
    staging = path.with_name(path.name + ".candidate")
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(to_cookie_file(text))
    result = verify(staging, video_id)
    if result["usable"]:
        os.replace(staging, path)
    else:
        staging.unlink(missing_ok=True)
    return {**result, "saved": bool(result["usable"])}
