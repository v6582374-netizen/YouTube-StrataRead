"""Anthropic Messages provider with extended thinking always enabled.

Design decisions (per user preference "only highest output quality"):

* Extended thinking is **always on** for Claude models. This is the feature
  that makes claude.ai feel like it "thinks hard"; without it the OpenAI-
  compatible fast path just emits a shallow answer.
* ``budget_tokens`` is set high enough that Claude Sonnet 4.x has room to
  reason over a two-hour transcript (default: 16000).
* ``max_tokens`` is bumped to 32000 so the visible Markdown answer has room
  to grow after the thinking block is consumed.
* When extended thinking is enabled Anthropic *requires* ``temperature=1.0``
  and explicitly forbids ``top_p`` / ``top_k`` modifications, so we override
  the caller's temperature on that branch.
* Response is streamed via the SDK's ``messages.stream()`` context manager
  to avoid HTTP timeouts on long generations (thinking + output can easily
  exceed 2 minutes).
"""
from __future__ import annotations

from bionic_youtube.ai.base import ChatRequest, LLMError, LLMProvider

# Tuned for 2h-long podcast transcripts; Sonnet 4.x caps at 64k output.
_THINKING_BUDGET = 16000
_MAX_TOKENS_DEFAULT = 32000
# Long-lived thinking streams can take minutes. Don't choke early.
_HTTP_TIMEOUT_SECONDS = 1200.0


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, pc) -> None:  # type: ignore[no-untyped-def]
        super().__init__(pc)
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMError("anthropic SDK is required. pip install anthropic") from e

        kwargs: dict[str, object] = {
            "api_key": pc.api_key,
            "timeout": _HTTP_TIMEOUT_SECONDS,
        }
        if pc.base_url:
            kwargs["base_url"] = pc.base_url
        self._client = anthropic.Anthropic(**kwargs)
        self._is_claude = "claude" in pc.model.lower()

    def _chat_impl(self, req: ChatRequest) -> str:
        params: dict[str, object] = {
            "model": req.model,
            "system": req.system,
            "messages": [{"role": "user", "content": req.user}],
        }
        if self._is_claude:
            # Extended thinking — the whole point of routing here.
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": _THINKING_BUDGET,
            }
            # Anthropic hard requirement: temperature must be 1.0 when
            # thinking is enabled; other sampling knobs must be left at
            # defaults. See: https://docs.anthropic.com/en/api/extended-thinking
            params["temperature"] = 1.0
            # Output budget must be >= thinking budget; give the visible
            # answer plenty of headroom on top.
            params["max_tokens"] = max(
                req.max_tokens or _MAX_TOKENS_DEFAULT,
                _THINKING_BUDGET + 8192,
            )
        else:
            params["temperature"] = req.temperature
            params["max_tokens"] = req.max_tokens or 4096

        text_parts: list[str] = []
        try:
            with self._client.messages.stream(**params) as stream:
                for chunk in stream.text_stream:
                    if not chunk:
                        continue
                    text_parts.append(chunk)
                    if req.on_stream is not None:
                        req.on_stream(chunk)
        except Exception as e:  # noqa: BLE001 - normalise to LLMError for retry
            raise LLMError(str(e)) from e

        text = "".join(text_parts).strip()
        if not text:
            raise LLMError("anthropic returned blank content")
        return text
