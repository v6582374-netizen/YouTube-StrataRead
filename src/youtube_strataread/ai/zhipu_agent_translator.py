"""Zhipu Agent API based translation preprocessor."""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from youtube_strataread.ai.base import LLMError
from youtube_strataread.ai.openai_utils import snapshot_suffix
from youtube_strataread.config import TranslationConfig

_AGENT_ENDPOINT = "https://open.bigmodel.cn/api/v1/agents"
_HTTP_TIMEOUT_SECONDS = 1200.0
_BAD_FINISH_REASONS = {"sensitive", "network_error"}
_LIMITED_TEXT_TRANSLATION_AGENTS = {
    "social_translation_agent",
    "social_literature_translation_agent",
}
_CHINESE_LANGS = {"zh", "zh-cn", "zh-hans", "zh-hant", "zh-tw"}


class ZhipuAgentTranslator:
    """Translate transcript text through Zhipu's official Agent API."""

    def __init__(
        self,
        config: TranslationConfig,
        *,
        api_key: str,
        endpoint: str = _AGENT_ENDPOINT,
    ) -> None:
        if not api_key:
            raise LLMError("missing GLM API key for Zhipu translation Agent")
        self.config = config
        self.api_key = api_key
        self.endpoint = endpoint

    def translate(
        self,
        text: str,
        *,
        subtitle_language: str | None = None,
        on_stream: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> str:
        chunks = _chunk_text(text, self.config.chunk_chars)
        if not chunks:
            return ""

        translated: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            if on_status is not None:
                on_status(f"translating... ({idx}/{len(chunks)})")
            translated.append(
                self._translate_chunk(
                    chunk,
                    subtitle_language=subtitle_language,
                    on_stream=on_stream,
                )
            )
        content = "\n".join(part.strip("\n") for part in translated).strip()
        if not content:
            raise LLMError("zhipu translation Agent returned blank content")
        return content

    def _translate_chunk(
        self,
        text: str,
        *,
        subtitle_language: str | None,
        on_stream: Callable[[str], None] | None,
    ) -> str:
        payload = {
            "agent_id": self.config.agent_id,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": text}],
                }
            ],
            "custom_variables": self._custom_variables(subtitle_language),
        }
        return self._post(payload, on_stream=on_stream)

    def _custom_variables(self, subtitle_language: str | None) -> dict[str, object]:
        agent_id = self.config.agent_id
        if agent_id == "general_translation":
            variables: dict[str, object] = {
                "source_lang": self.config.source_lang,
                "target_lang": self.config.target_lang,
                "strategy": self.config.strategy,
            }
            if self.config.strategy == "general" and self.config.suggestion:
                variables["strategy_config"] = {
                    "general": {"suggestion": self.config.suggestion}
                }
            return variables

        if agent_id in _LIMITED_TEXT_TRANSLATION_AGENTS:
            target_lang = _require_limited_language(self.config.target_lang, "target_lang")
            variables = {
                "source_lang": _source_lang_for_limited_agent(
                    self.config.source_lang,
                    subtitle_language,
                ),
                "target_lang": target_lang,
            }
            if agent_id == "social_translation_agent":
                variables["style"] = "通用风格"
            return variables

        if agent_id == "subtitle_translation_agent":
            return {"language": _subtitle_agent_target(self.config.target_lang)}

        raise LLMError(f"unsupported translation agent '{agent_id}'")

    def _post(
        self,
        payload: Mapping[str, object],
        *,
        on_stream: Callable[[str], None] | None,
    ) -> str:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "text/event-stream, application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
                content_type = _header_value(response, "Content-Type")
                if "text/event-stream" in content_type.lower():
                    return _read_sse_response(response, on_stream=on_stream)
                body = response.read().decode("utf-8")
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace").strip()
            reason = detail or str(e)
            raise LLMError(f"zhipu translation Agent request failed ({e.code}): {reason}") from e
        except URLError as e:
            raise LLMError(f"zhipu translation Agent request failed: {e.reason}") from e
        except TimeoutError as e:
            raise LLMError("zhipu translation Agent request timed out") from e

        try:
            payload_obj = json.loads(body)
        except json.JSONDecodeError as e:
            raise LLMError("zhipu translation Agent returned invalid JSON") from e
        _raise_for_api_error(payload_obj)
        content = _extract_agent_text(payload_obj).strip()
        if not content:
            raise LLMError("zhipu translation Agent returned blank content")
        if on_stream is not None:
            on_stream(content)
        return content


def is_chinese_subtitle_language(language: str | None) -> bool:
    if not language:
        return False
    normalized = language.strip().lower().replace("_", "-")
    return normalized in _CHINESE_LANGS or normalized.startswith("zh-")


def _read_sse_response(
    response: Iterable[bytes],
    *,
    on_stream: Callable[[str], None] | None,
) -> str:
    parts: list[str] = []
    content_buffer = ""
    for data in _iter_sse_data(response):
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as e:
            raise LLMError("zhipu translation Agent returned invalid stream JSON") from e
        _raise_for_api_error(payload)
        current = _extract_agent_text(payload)
        if not current:
            continue
        content_buffer, chunk = snapshot_suffix(content_buffer, current)
        if not chunk:
            continue
        parts.append(chunk)
        if on_stream is not None:
            on_stream(chunk)

    content = "".join(parts).strip()
    if not content:
        raise LLMError("zhipu translation Agent returned blank content")
    return content


def _iter_sse_data(response: Iterable[bytes]) -> Iterable[str]:
    data_lines: list[str] = []
    for raw in response:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield "\n".join(data_lines)


def _extract_agent_text(payload: Mapping[str, Any]) -> str:
    texts: list[str] = []
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return ""
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        finish_reason = choice.get("finish_reason")
        if isinstance(finish_reason, str) and finish_reason in _BAD_FINISH_REASONS:
            raise LLMError(f"zhipu translation Agent stopped with {finish_reason}")

        messages = choice.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, Mapping):
                    texts.append(_content_to_text(message.get("content")))

        message = choice.get("message")
        if isinstance(message, Mapping):
            texts.append(_content_to_text(message.get("content")))

        delta = choice.get("delta")
        if isinstance(delta, Mapping):
            texts.append(_content_to_text(delta.get("content")))
    return "".join(texts)


def _content_to_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Mapping):
        text = content.get("text") or content.get("value")
        return text if isinstance(text, str) else ""
    if isinstance(content, list):
        return "".join(_content_to_text(item) for item in content)
    text = getattr(content, "text", None) or getattr(content, "value", None)
    return text if isinstance(text, str) else ""


def _raise_for_api_error(payload: Mapping[str, Any]) -> None:
    error = payload.get("error")
    if isinstance(error, Mapping):
        message = error.get("message") or error.get("code") or "unknown error"
        raise LLMError(f"zhipu translation Agent error: {message}")
    code = payload.get("code")
    if code not in {None, 0, "0", "success"}:
        message = payload.get("message") or payload.get("msg") or code
        raise LLMError(f"zhipu translation Agent error: {message}")


def _chunk_text(text: str, max_chars: int) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for piece in text.splitlines(keepends=True):
        if len(piece) > max_chars:
            if current:
                chunks.append("".join(current))
                current = []
                size = 0
            chunks.extend(
                piece[start : start + max_chars]
                for start in range(0, len(piece), max_chars)
            )
            continue
        if current and size + len(piece) > max_chars:
            chunks.append("".join(current))
            current = []
            size = 0
        current.append(piece)
        size += len(piece)
    if current:
        chunks.append("".join(current))
    return chunks


def _source_lang_for_limited_agent(
    configured_source_lang: str,
    subtitle_language: str | None,
) -> str:
    if configured_source_lang in {"en", "zh-CN"}:
        return configured_source_lang
    if is_chinese_subtitle_language(subtitle_language):
        return "zh-CN"
    normalized = (subtitle_language or "").strip().lower().replace("_", "-")
    if normalized in {"en", "en-us", "en-gb"} or normalized.startswith("en-"):
        return "en"
    raise LLMError(
        "selected translation Agent only supports source_lang en or zh-CN"
    )


def _require_limited_language(value: str, field_name: str) -> str:
    if value not in {"en", "zh-CN"}:
        raise LLMError(
            f"selected translation Agent only supports {field_name} en or zh-CN"
        )
    return value


def _subtitle_agent_target(target_lang: str) -> str:
    mapping = {
        "en": "English",
        "en-US": "English",
        "en-GB": "English",
        "ja": "Japanese",
        "ko": "Korean",
    }
    try:
        return mapping[target_lang]
    except KeyError as e:
        raise LLMError(
            "subtitle_translation_agent only supports target languages en, ja, and ko"
        ) from e


def _header_value(response: object, name: str) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    value = headers.get(name, "")
    return value if isinstance(value, str) else ""

