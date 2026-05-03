from __future__ import annotations

import json
from typing import Any
from urllib.request import Request

import youtube_strataread.ai.zhipu_agent_translator as zhipu
from youtube_strataread.config import TranslationConfig


class FakeResponse:
    def __init__(self, *, content_type: str, body: bytes = b"", lines: list[bytes] | None = None) -> None:
        self.headers = {"Content-Type": content_type}
        self.body = body
        self.lines = lines or []

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False

    def read(self) -> bytes:
        return self.body

    def __iter__(self):  # noqa: ANN204
        return iter(self.lines)


def test_zhipu_agent_translator_streams_and_dedupes_snapshots(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        seen["timeout"] = timeout
        seen["authorization"] = request.get_header("Authorization")
        seen["payload"] = json.loads((request.data or b"").decode("utf-8"))
        return FakeResponse(
            content_type="text/event-stream",
            lines=[
                _sse({"choices": [{"messages": [{"content": {"type": "text", "text": "你好"}}]}]}),
                b"\n",
                _sse({"choices": [{"messages": [{"content": {"type": "text", "text": "你好世界"}}]}]}),
                b"\n",
                b"data: [DONE]\n",
                b"\n",
            ],
        )

    monkeypatch.setattr(zhipu, "urlopen", fake_urlopen)
    translator = zhipu.ZhipuAgentTranslator(
        TranslationConfig(),
        api_key="glm-key",
    )
    chunks: list[str] = []

    result = translator.translate("Hello world", subtitle_language="en", on_stream=chunks.append)

    assert result == "你好世界"
    assert chunks == ["你好", "世界"]
    assert seen["authorization"] == "Bearer glm-key"
    assert seen["payload"]["agent_id"] == "general_translation"
    assert seen["payload"]["stream"] is True
    assert seen["payload"]["messages"][0]["content"][0]["text"] == "Hello world"
    assert seen["payload"]["custom_variables"]["source_lang"] == "auto"
    assert seen["payload"]["custom_variables"]["target_lang"] == "zh-CN"
    assert seen["payload"]["custom_variables"]["strategy"] == "general"


def test_zhipu_agent_translator_reads_json_response(monkeypatch) -> None:
    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        return FakeResponse(
            content_type="application/json",
            body=json.dumps(
                {
                    "choices": [
                        {
                            "messages": [
                                {
                                    "role": "assistant",
                                    "content": [{"type": "text", "text": "你好"}],
                                }
                            ],
                            "finish_reason": "stop",
                        }
                    ]
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )

    monkeypatch.setattr(zhipu, "urlopen", fake_urlopen)
    translator = zhipu.ZhipuAgentTranslator(TranslationConfig(), api_key="glm-key")

    assert translator.translate("Hello", subtitle_language="en") == "你好"


def _sse(payload: dict[str, object]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n".encode()
