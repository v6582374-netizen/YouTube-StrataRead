"""GLM native provider with thinking mode enabled by default."""
from __future__ import annotations

from typing import Any

from youtube_strataread.ai.base import ChatRequest, LLMError, LLMProvider
from youtube_strataread.ai.openai_utils import content_to_text

_HTTP_TIMEOUT_SECONDS = 1200.0
_MAX_TOKENS_DEFAULT = 32000


class GLMProvider(LLMProvider):
    name = "glm"

    def __init__(self, pc) -> None:  # type: ignore[no-untyped-def]
        super().__init__(pc)
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("openai SDK is required. pip install openai") from e

        kwargs: dict[str, object] = {
            "api_key": pc.api_key,
            "timeout": _HTTP_TIMEOUT_SECONDS,
        }
        if pc.base_url:
            kwargs["base_url"] = pc.base_url
        self._client = OpenAI(**kwargs)

    def _chat_impl(self, req: ChatRequest) -> str:
        params: dict[str, object] = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "stream": True,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens or _MAX_TOKENS_DEFAULT,
            "extra_body": {"thinking": {"type": "enabled"}},
        }

        parts: list[str] = []
        try:
            stream = self._client.chat.completions.create(**params)
            for event in stream:
                delta = _first_delta(event)
                if delta is None:
                    continue
                chunk = content_to_text(getattr(delta, "content", None))
                if not chunk:
                    continue
                parts.append(chunk)
                if req.on_stream is not None:
                    req.on_stream(chunk)
        except Exception as e:  # noqa: BLE001
            raise LLMError(str(e)) from e

        content = "".join(parts).strip()
        if not content:
            raise LLMError("glm returned blank content")
        return content


def _first_delta(event: Any) -> object | None:
    choices = getattr(event, "choices", None) or []
    if not choices:
        return None
    return getattr(choices[0], "delta", None)
