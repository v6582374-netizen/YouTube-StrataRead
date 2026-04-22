from __future__ import annotations

from types import SimpleNamespace

from youtube_strataread.ai.base import ChatRequest
from youtube_strataread.ai.minimax_provider import MiniMaxProvider
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


def test_minimax_splits_reasoning_and_dedupes_snapshot_stream() -> None:
    client = FakeOpenAIClient(
        [
            _stream_event(content="Hello", reasoning="thought 1"),
            _stream_event(content="Hello world", reasoning="thought 2"),
        ]
    )
    provider = _make_provider(client)
    seen_chunks: list[str] = []

    result = provider._chat_impl(_request(on_stream=seen_chunks.append))

    assert result == "Hello world"
    assert seen_chunks == ["Hello", " world"]
    assert client.calls[0]["extra_body"] == {"reasoning_split": True}


def _make_provider(client: FakeOpenAIClient) -> MiniMaxProvider:
    provider = MiniMaxProvider.__new__(MiniMaxProvider)
    provider.pc = ProviderConfig(
        name="minimax",
        model="MiniMax-M2.7",
        base_url="https://api.minimaxi.com/v1",
        api_key="test-key",
        api_flavor="minimax",
    )
    provider._client = client
    return provider


def _request(*, on_stream=None) -> ChatRequest:  # noqa: ANN001
    return ChatRequest(
        system="system",
        user="user",
        model="MiniMax-M2.7",
        temperature=0.3,
        on_stream=on_stream,
    )


def _stream_event(*, content: str, reasoning: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    reasoning_details=[{"type": "text", "text": reasoning}],
                )
            )
        ]
    )
