"""Provider abstraction for LLM chat calls.

Supports DeepSeek / OpenAI (shared openai SDK) and Anthropic.
Handles retries and common error normalisation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from youtube_strataread.config import ProviderConfig


class LLMError(RuntimeError):
    """Raised when an LLM call fails irrecoverably."""


class NonRetryableLLMError(LLMError):
    """Raised for failures that should bypass the outer retry loop."""


@dataclass
class ChatRequest:
    system: str
    user: str
    model: str
    temperature: float = 0.2
    max_tokens: int | None = None
    # Optional per-call callback receiving streamed text chunks (decoded
    # strings). Providers that stream internally should call this on every
    # delta so the CLI can drive a progress bar.
    on_stream: Callable[[str], None] | None = field(default=None, repr=False)
    # Optional callback for user-visible pipeline status changes that are not
    # tied to visible output chunks, such as switching to a fallback strategy.
    on_status: Callable[[str], None] | None = field(default=None, repr=False)


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, pc: ProviderConfig) -> None:
        self.pc = pc
        if not pc.api_key:
            raise LLMError(
                f"missing API key for provider '{pc.name}'. "
                f"Run: by config set {pc.name} --key <API_KEY>"
            )

    @abstractmethod
    def _chat_impl(self, req: ChatRequest) -> str: ...

    @retry(
        reraise=True,
        retry=retry_if_exception(
            lambda exc: isinstance(exc, LLMError)
            and not isinstance(exc, NonRetryableLLMError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=1, max=20),
    )
    def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
        on_stream: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> str:
        req = ChatRequest(
            system=system,
            user=user,
            model=model or self.pc.model,
            temperature=temperature,
            max_tokens=max_tokens,
            on_stream=on_stream,
            on_status=on_status,
        )
        try:
            return self._chat_impl(req)
        except (LLMError, NonRetryableLLMError):
            raise
        except Exception as e:  # noqa: BLE001 - normalise to LLMError for retry
            raise LLMError(str(e)) from e


def get_provider(pc: ProviderConfig) -> LLMProvider:
    """Factory returning a concrete provider instance, dispatched by wire flavor.

    * ``"anthropic"`` → :class:`AnthropicProvider` (native Messages API with
      extended thinking enabled).
    * ``"gemini"``   → :class:`GeminiProvider` (Google GenAI with thinking_config).
    * ``"openai"``   → :class:`OpenAICompatibleProvider` (Chat Completions;
      automatically sets ``reasoning_effort="high"`` for reasoning-class models).
    """
    if pc.api_flavor == "anthropic":
        from youtube_strataread.ai.anthropic_provider import AnthropicProvider
        return AnthropicProvider(pc)
    if pc.api_flavor == "gemini":
        from youtube_strataread.ai.gemini_provider import GeminiProvider
        return GeminiProvider(pc)
    if pc.api_flavor == "openai":
        from youtube_strataread.ai.openai_provider import OpenAICompatibleProvider
        return OpenAICompatibleProvider(pc)
    raise LLMError(f"unknown api_flavor '{pc.api_flavor}' for provider '{pc.name}'")
