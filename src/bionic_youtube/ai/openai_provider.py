"""OpenAI Chat-Completions-compatible provider.

Used by both ``openai`` (the real OpenAI API) and ``compat`` (any third-party
relay that speaks the Chat Completions wire format).

Deep thinking is unlocked by passing ``reasoning_effort="high"`` on reasoning-
class models. We detect those by model-name prefix. For non-reasoning models
the parameter is silently dropped to avoid 4xx errors from strict servers.
"""
from __future__ import annotations

import re

from bionic_youtube.ai.base import ChatRequest, LLMError, LLMProvider

# Heuristic pattern for models that accept ``reasoning_effort``.
# Covers OpenAI's o-series, GPT-5 reasoning variants, DeepSeek-Reasoner,
# and anything with an explicit ``thinking`` / ``reasoning`` / ``:r1`` marker.
_REASONING_MODEL_RE = re.compile(
    r"^(o[134]-?|o4-mini)|^gpt-5(?!-chat)|deepseek-reasoner|reasoner|thinking|:r\d",
    re.IGNORECASE,
)


def _supports_reasoning_effort(model: str) -> bool:
    return bool(_REASONING_MODEL_RE.search(model))


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compat"

    def __init__(self, pc) -> None:  # type: ignore[no-untyped-def]
        super().__init__(pc)
        if pc.name == "compat" and not pc.base_url:
            raise LLMError(
                "compat provider needs a base_url. Run: "
                "by config set compat --base-url https://your-relay/v1 --key <API_KEY>"
            )
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("openai SDK is required. pip install openai") from e
        kwargs: dict[str, object] = {"api_key": pc.api_key}
        if pc.base_url:
            kwargs["base_url"] = pc.base_url
        # Long thinking streams need a generous read timeout.
        kwargs["timeout"] = 1200.0
        self._client = OpenAI(**kwargs)
        self._reasoning = _supports_reasoning_effort(pc.model)

    def _chat_impl(self, req: ChatRequest) -> str:
        params: dict[str, object] = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "stream": True,
        }
        if self._reasoning:
            # OpenAI + most relays accept this; it unlocks the hidden chain of
            # thought on o-series / GPT-5 reasoning / DeepSeek-Reasoner.
            params["reasoning_effort"] = "high"
            # Reasoning models ignore temperature; omit it to be safe.
        else:
            params["temperature"] = req.temperature
            if req.max_tokens is not None:
                params["max_tokens"] = req.max_tokens

        try:
            stream = self._client.chat.completions.create(**params)
        except Exception as e:  # noqa: BLE001
            raise LLMError(str(e)) from e

        parts: list[str] = []
        try:
            for event in stream:
                if not getattr(event, "choices", None):
                    continue
                delta = event.choices[0].delta
                chunk = getattr(delta, "content", None)
                if not chunk:
                    continue
                parts.append(chunk)
                if req.on_stream is not None:
                    req.on_stream(chunk)
        except Exception as e:  # noqa: BLE001
            raise LLMError(str(e)) from e

        content = "".join(parts)
        if not content.strip():
            raise LLMError("model returned blank content")
        return content
