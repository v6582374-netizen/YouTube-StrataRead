from __future__ import annotations

from types import SimpleNamespace

from youtube_strataread.ai.base import ChatRequest
from youtube_strataread.ai.deepseek_provider import DeepSeekProvider
from youtube_strataread.config import ProviderConfig


class FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **params: object) -> object:
        self.calls.append(dict(params))
        return self.response


def test_deepseek_reasoner_hides_reasoning_content() -> None:
    client = FakeOpenAIClient(
        [
            _stream_event(reasoning="first thought", content="Hello"),
            _stream_event(reasoning="second thought", content=" world"),
        ]
    )
    provider = _make_provider(client, model="deepseek-reasoner")
    seen_chunks: list[str] = []

    result = provider._chat_impl(_request(model="deepseek-reasoner", on_stream=seen_chunks.append))

    assert result == "Hello world"
    assert seen_chunks == ["Hello", " world"]
    assert "extra_body" not in client.calls[0]


def test_deepseek_chat_enables_thinking_mode() -> None:
    client = FakeOpenAIClient([_stream_event(content="ok")])
    provider = _make_provider(client, model="deepseek-chat")

    result = provider._chat_impl(_request(model="deepseek-chat"))

    assert result == "ok"
    assert client.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


def _make_provider(client: FakeOpenAIClient, *, model: str) -> DeepSeekProvider:
    provider = DeepSeekProvider.__new__(DeepSeekProvider)
    provider.pc = ProviderConfig(
        name="deepseek",
        model=model,
        base_url="https://api.deepseek.com",
        api_key="test-key",
        api_flavor="deepseek",
    )
    provider._client = client
    return provider


def _request(*, model: str, on_stream=None) -> ChatRequest:  # noqa: ANN001
    return ChatRequest(
        system="system",
        user="user",
        model=model,
        temperature=0.3,
        on_stream=on_stream,
    )


def _stream_event(*, content: str = "", reasoning: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning,
                )
            )
        ]
    )
