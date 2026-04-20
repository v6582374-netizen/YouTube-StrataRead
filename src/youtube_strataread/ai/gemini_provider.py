"""Google Gemini provider with thinking enabled by default.

Gemini 2.5 models support an opaque "thinking" phase before answering. We
enable it via ``thinking_config`` on every call:

* ``thinking_budget = -1`` → dynamic / "think as much as needed".
* ``include_thoughts = False`` → keep the reasoning hidden from the final
  answer (same behaviour as the Claude path; we only want the final Markdown).

Streaming is used so the orchestrator's progress bar can tick as deltas
arrive — long thinking + long answer on a 2h podcast can take minutes.
"""
from __future__ import annotations

from youtube_strataread.ai.base import ChatRequest, LLMError, LLMProvider

_THINKING_BUDGET = -1  # -1 = dynamic/auto on Gemini 2.5


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, pc) -> None:  # type: ignore[no-untyped-def]
        super().__init__(pc)
        try:
            from google import genai  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise LLMError(
                "google-genai SDK is required. pip install google-genai"
            ) from e
        from google import genai

        client_kwargs: dict[str, object] = {"api_key": pc.api_key}
        # ``base_url`` for Gemini is niche (Vertex AI relay). If set, pass it
        # through via ``http_options``.
        if pc.base_url:
            from google.genai import types as genai_types
            client_kwargs["http_options"] = genai_types.HttpOptions(
                base_url=pc.base_url,
            )
        self._client = genai.Client(**client_kwargs)
        self._is_thinking_model = self._model_supports_thinking(pc.model)

    @staticmethod
    def _model_supports_thinking(model: str) -> bool:
        # Gemini 2.5 Pro / Flash / Flash-Lite all support thinking_config.
        return model.startswith("gemini-2.5") or "thinking" in model.lower()

    def _chat_impl(self, req: ChatRequest) -> str:
        from google.genai import types as genai_types

        thinking_config = None
        if self._is_thinking_model:
            thinking_config = genai_types.ThinkingConfig(
                thinking_budget=_THINKING_BUDGET,
                include_thoughts=False,
            )

        config = genai_types.GenerateContentConfig(
            system_instruction=req.system,
            temperature=req.temperature,
            max_output_tokens=req.max_tokens or 32000,
            thinking_config=thinking_config,
        )

        parts: list[str] = []
        try:
            stream = self._client.models.generate_content_stream(
                model=req.model,
                contents=req.user,
                config=config,
            )
            for chunk in stream:
                text = getattr(chunk, "text", None) or ""
                if not text:
                    continue
                parts.append(text)
                if req.on_stream is not None:
                    req.on_stream(text)
        except Exception as e:  # noqa: BLE001
            raise LLMError(str(e)) from e

        content = "".join(parts).strip()
        if not content:
            raise LLMError("gemini returned blank content")
        return content
