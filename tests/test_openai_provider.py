from __future__ import annotations

from types import SimpleNamespace

import pytest

from youtube_strataread.ai.base import (
    ChatRequest,
    LLMError,
    NonRetryableLLMError,
)
from youtube_strataread.ai.openai_provider import OpenAICompatibleProvider
from youtube_strataread.config import ProviderConfig

APITimeoutError = type("APITimeoutError", (Exception,), {})
AuthenticationError = type("AuthenticationError", (Exception,), {})
BadRequestError = type("BadRequestError", (Exception,), {})
RateLimitError = type("RateLimitError", (Exception,), {})


class FakeOpenAIClient:
    def __init__(self, actions: list[object]) -> None:
        self._actions = list(actions)
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create_default),
        )

    def with_options(self, **options: object) -> SimpleNamespace:
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **params: self._create(options=options, **params)
                )
            )
        )

    def _create_default(self, **params: object) -> object:
        return self._create(options={}, **params)

    def _create(self, *, options: dict[str, object], **params: object) -> object:
        self.calls.append({"options": dict(options), "params": dict(params)})
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def test_compat_falls_back_to_full_response_on_first_chunk_timeout() -> None:
    client = FakeOpenAIClient(
        [
            APITimeoutError("request timed out"),
            _full_response("final answer"),
        ]
    )
    provider = _make_provider(client, compat=True)
    seen_status: list[str] = []
    seen_chunks: list[str] = []

    result = provider._chat_impl(
        _request(on_status=seen_status.append, on_stream=seen_chunks.append)
    )

    assert result == "final answer"
    assert seen_status == ["thinking... (retrying full response)"]
    assert seen_chunks == ["final answer"]
    assert client.calls[0]["options"] == {"timeout": 25.0, "max_retries": 0}
    assert client.calls[0]["params"]["stream"] is True
    assert client.calls[0]["params"]["model"] == "claude-sonnet-4-6"
    assert client.calls[1]["options"] == {"timeout": 1200.0, "max_retries": 0}
    assert client.calls[1]["params"]["stream"] is False
    assert client.calls[1]["params"]["model"] == "claude-sonnet-4-6"


def test_compat_falls_back_on_cancel_timeout_429() -> None:
    error = RateLimitError(
        "Error code: 429 - {'error': {'message': 'cancel timeout: 30.000427s', "
        "'type': 'do_request_failed'}}"
    )
    error.status_code = 429  # type: ignore[attr-defined]
    client = FakeOpenAIClient([error, _full_response("recovered")])
    provider = _make_provider(client, compat=True)

    result = provider._chat_impl(_request())

    assert result == "recovered"
    assert len(client.calls) == 2
    assert client.calls[1]["params"]["stream"] is False


def test_compat_does_not_fallback_after_visible_chunk() -> None:
    client = FakeOpenAIClient(
        [_stream_response("hi", error=APITimeoutError("read timed out"))]
    )
    provider = _make_provider(client, compat=True)
    seen_chunks: list[str] = []

    with pytest.raises(LLMError, match="read timed out"):
        provider._chat_impl(_request(on_stream=seen_chunks.append))

    assert seen_chunks == ["hi"]
    assert len(client.calls) == 1


def test_compat_does_not_fallback_on_auth_error() -> None:
    client = FakeOpenAIClient([AuthenticationError("invalid api key")])
    provider = _make_provider(client, compat=True)

    with pytest.raises(LLMError, match="invalid api key"):
        provider._chat_impl(_request())

    assert len(client.calls) == 1


def test_compat_does_not_fallback_on_bad_request() -> None:
    client = FakeOpenAIClient([BadRequestError("unsupported parameter: reasoning_effort")])
    provider = _make_provider(client, compat=True)

    with pytest.raises(LLMError, match="unsupported parameter"):
        provider._chat_impl(_request())

    assert len(client.calls) == 1


def test_compat_fallback_failure_is_non_retryable() -> None:
    client = FakeOpenAIClient(
        [
            APITimeoutError("request timed out"),
            RateLimitError("upstream overloaded"),
        ]
    )
    provider = _make_provider(client, compat=True)

    with pytest.raises(NonRetryableLLMError, match="upstream overloaded"):
        provider._chat_impl(_request())

    assert len(client.calls) == 2


def test_build_params_uses_request_model_for_reasoning_effort() -> None:
    client = FakeOpenAIClient([_stream_response("ok")])
    provider = _make_provider(client, compat=False, model="gpt-4o-mini")

    provider._chat_impl(_request(model="gpt-5"))

    assert client.calls[0]["params"]["reasoning_effort"] == "high"
    assert "temperature" not in client.calls[0]["params"]


def test_compat_omits_temperature_by_default() -> None:
    client = FakeOpenAIClient([_stream_response("ok")])
    provider = _make_provider(client, compat=True, use_temperature=False)

    provider._chat_impl(_request(model="claude-opus-4-7"))

    assert "temperature" not in client.calls[0]["params"]


def test_compat_can_explicitly_send_temperature() -> None:
    client = FakeOpenAIClient([_stream_response("ok")])
    provider = _make_provider(client, compat=True, use_temperature=True)

    provider._chat_impl(_request(model="claude-opus-4-7"))

    assert client.calls[0]["params"]["temperature"] == 0.3


def _make_provider(
    client: FakeOpenAIClient,
    *,
    compat: bool,
    model: str = "claude-sonnet-4-6",
    use_temperature: bool = True,
) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.pc = ProviderConfig(
        name="compat" if compat else "openai",
        model=model,
        base_url="https://relay.example/v1" if compat else None,
        api_key="test-key",
        use_temperature=use_temperature,
        api_flavor="openai",
    )
    provider._client = client
    provider._compat_mode = compat
    return provider


def _request(
    *,
    model: str = "claude-sonnet-4-6",
    on_stream=None,  # noqa: ANN001
    on_status=None,  # noqa: ANN001
) -> ChatRequest:
    return ChatRequest(
        system="system",
        user="user",
        model=model,
        temperature=0.3,
        on_stream=on_stream,
        on_status=on_status,
    )


def _stream_response(*chunks: str, error: Exception | None = None):
    def iterator():
        for chunk in chunks:
            yield _stream_event(chunk)
        if error is not None:
            raise error

    return iterator()


def _stream_event(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
    )


def _full_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )
