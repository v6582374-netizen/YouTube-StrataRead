from __future__ import annotations

from types import SimpleNamespace

from youtube_strataread.ai.base import ChatRequest
from youtube_strataread.ai.glm_provider import GLMProvider
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


def test_glm_enables_thinking_and_hides_reasoning_content() -> None:
    client = FakeOpenAIClient(
        [
            _stream_event(reasoning="思考中", content="Hello"),
            _stream_event(reasoning="继续思考", content=" world"),
        ]
    )
    provider = _make_provider(client)
    seen_chunks: list[str] = []

    result = provider._chat_impl(_request(on_stream=seen_chunks.append))

    assert result == "Hello world"
    assert seen_chunks == ["Hello", " world"]
    assert client.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


def _make_provider(client: FakeOpenAIClient) -> GLMProvider:
    provider = GLMProvider.__new__(GLMProvider)
    provider.pc = ProviderConfig(
        name="glm",
        model="glm-5.1",
        base_url="https://open.bigmodel.cn/api/paas/v4/",
        api_key="test-key",
        api_flavor="glm",
    )
    provider._client = client
    return provider


def _request(*, on_stream=None) -> ChatRequest:  # noqa: ANN001
    return ChatRequest(
        system="system",
        user="user",
        model="glm-5.1",
        temperature=0.3,
        on_stream=on_stream,
    )


def _stream_event(*, content: str, reasoning: str) -> SimpleNamespace:
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
