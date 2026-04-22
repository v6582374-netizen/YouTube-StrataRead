"""OpenAI Chat-Completions-compatible provider.

Used by both ``openai`` (the real OpenAI API) and ``compat`` (any third-party
relay that speaks the Chat Completions wire format).

Deep thinking is unlocked by passing ``reasoning_effort="high"`` on reasoning-
class models. We detect those by model-name prefix. For non-reasoning models
the parameter is silently dropped to avoid 4xx errors from strict servers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from youtube_strataread.ai.base import (
    ChatRequest,
    LLMError,
    LLMProvider,
    NonRetryableLLMError,
)

# Heuristic pattern for models that accept ``reasoning_effort``.
# Covers OpenAI's o-series, GPT-5 reasoning variants, DeepSeek-Reasoner,
# and anything with an explicit ``thinking`` / ``reasoning`` / ``:r1`` marker.
_REASONING_MODEL_RE = re.compile(
    r"^(o[134]-?|o4-mini)|^gpt-5(?!-chat)|deepseek-reasoner|reasoner|thinking|:r\d",
    re.IGNORECASE,
)


def _supports_reasoning_effort(model: str) -> bool:
    return bool(_REASONING_MODEL_RE.search(model))


_HTTP_TIMEOUT_SECONDS = 1200.0
_FIRST_CHUNK_TIMEOUT_SECONDS = 25.0
_FALLBACK_STATUS = "thinking... (retrying full response)"
_NON_RECOVERABLE_ERROR_NAMES = {
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "UnprocessableEntityError",
}
_RECOVERABLE_COMPAT_ERROR_MARKERS = (
    "cancel timeout",
    "do_request_failed",
    "first chunk",
    "first byte",
    "read timeout",
    "timed out",
)
_TIMEOUT_ERROR_NAMES = {
    "APITimeoutError",
    "ConnectTimeout",
    "ReadTimeout",
    "ReadTimeoutError",
    "TimeoutError",
    "TimeoutException",
    "WriteTimeout",
}


@dataclass
class _StreamAttemptFailed(RuntimeError):
    error: Exception
    saw_visible_chunk: bool

    def __str__(self) -> str:
        return str(self.error)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compat"

    def __init__(self, pc) -> None:  # type: ignore[no-untyped-def]
        super().__init__(pc)
        if pc.name == "compat" and not pc.base_url:
            if pc.profile_name and pc.profile_name != "default":
                hint = (
                    "by config compat set "
                    f"{pc.profile_name} --base-url https://your-relay/v1 --key <API_KEY>"
                )
            else:
                hint = "by config set compat --base-url https://your-relay/v1 --key <API_KEY>"
            raise LLMError(
                f"compat provider needs a base_url. Run: {hint}"
            )
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("openai SDK is required. pip install openai") from e
        kwargs: dict[str, object] = {"api_key": pc.api_key}
        if pc.base_url:
            kwargs["base_url"] = pc.base_url
        # Long thinking streams need a generous read timeout.
        kwargs["timeout"] = _HTTP_TIMEOUT_SECONDS
        self._client = OpenAI(**kwargs)
        self._compat_mode = pc.name == "compat"

    def _chat_impl(self, req: ChatRequest) -> str:
        if self._compat_mode:
            return self._chat_compat(req)
        return self._stream_chat(self._client, req)

    def _chat_compat(self, req: ChatRequest) -> str:
        stream_client = self._client.with_options(
            timeout=_FIRST_CHUNK_TIMEOUT_SECONDS,
            max_retries=0,
        )
        try:
            return self._stream_chat(stream_client, req)
        except _StreamAttemptFailed as failure:
            if failure.saw_visible_chunk or not self._should_fallback_after_stream_failure(
                failure.error
            ):
                raise self._as_llm_error(failure.error) from failure.error
            if req.on_status is not None:
                req.on_status(_FALLBACK_STATUS)
            fallback_client = self._client.with_options(
                timeout=_HTTP_TIMEOUT_SECONDS,
                max_retries=0,
            )
            try:
                return self._full_response_chat(fallback_client, req)
            except Exception as e:  # noqa: BLE001
                raise NonRetryableLLMError(str(e)) from e

    def _build_params(self, req: ChatRequest, *, stream: bool) -> dict[str, object]:
        params: dict[str, object] = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "stream": stream,
        }
        if _supports_reasoning_effort(req.model):
            # OpenAI + most relays accept this; it unlocks the hidden chain of
            # thought on o-series / GPT-5 reasoning / DeepSeek-Reasoner.
            params["reasoning_effort"] = "high"
            # Reasoning models ignore temperature; omit it to be safe.
        else:
            params["temperature"] = req.temperature
            if req.max_tokens is not None:
                params["max_tokens"] = req.max_tokens
        return params

    def _stream_chat(self, client: Any, req: ChatRequest) -> str:
        params = self._build_params(req, stream=True)
        try:
            stream = client.chat.completions.create(**params)
        except Exception as e:  # noqa: BLE001
            raise _StreamAttemptFailed(e, saw_visible_chunk=False) from e

        parts: list[str] = []
        saw_visible_chunk = False
        try:
            for event in stream:
                if not getattr(event, "choices", None):
                    continue
                delta = event.choices[0].delta
                chunk = self._content_to_text(getattr(delta, "content", None))
                if not chunk:
                    continue
                saw_visible_chunk = True
                parts.append(chunk)
                if req.on_stream is not None:
                    req.on_stream(chunk)
        except Exception as e:  # noqa: BLE001
            raise _StreamAttemptFailed(e, saw_visible_chunk=saw_visible_chunk) from e

        content = "".join(parts)
        if not content.strip():
            raise _StreamAttemptFailed(LLMError("model returned blank content"), saw_visible_chunk=False)
        return content

    def _full_response_chat(self, client: Any, req: ChatRequest) -> str:
        params = self._build_params(req, stream=False)
        try:
            response = client.chat.completions.create(**params)
        except Exception as e:  # noqa: BLE001
            raise LLMError(str(e)) from e

        content = ""
        choices = getattr(response, "choices", None) or []
        if choices:
            content = self._content_to_text(getattr(choices[0].message, "content", None))
        content = content.strip()
        if not content:
            raise LLMError("model returned blank content")
        if req.on_stream is not None:
            req.on_stream(content)
        return content

    @staticmethod
    def _content_to_text(content: object) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                part
                for item in content
                for part in (
                    item
                    if isinstance(item, str)
                    else getattr(item, "text", None) or getattr(item, "value", None) or ""
                ,)
                if isinstance(part, str)
            )
        text = getattr(content, "text", None) or getattr(content, "value", None)
        return text if isinstance(text, str) else ""

    @staticmethod
    def _as_llm_error(error: Exception) -> LLMError:
        if isinstance(error, LLMError):
            return error
        return LLMError(str(error))

    def _should_fallback_after_stream_failure(self, error: Exception) -> bool:
        name = error.__class__.__name__
        if name in _NON_RECOVERABLE_ERROR_NAMES:
            return False
        message = str(error).lower()
        if any(marker in message for marker in _RECOVERABLE_COMPAT_ERROR_MARKERS):
            return True
        return name in _TIMEOUT_ERROR_NAMES
