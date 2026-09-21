"""Tests for provider key detection + the live (read-only) Test/verify path. SDK-free: the
single httpx.get is monkeypatched so no network is touched."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from coworker.providers import detect_provider, verify_provider_key


# -- detect_provider ------------------------------------------------------------
@pytest.mark.parametrize(
    "key,expected",
    [
        ("sk-ant-api03-abc", "anthropic"),
        ("sk-or-v1-abc", "openrouter"),
        ("AIzaSyAbc123", "gemini"),
        ("sk-proj-abc", "openai"),
        ("sk_live_abc", "openai"),
        ("", None),
        ("   ", None),
        ("nonsense", None),
    ],
)
def test_detect_provider(key, expected):
    assert detect_provider(key) == expected


# -- verify_provider_key: status-code mapping + per-provider request shape -------
def _patch_get(monkeypatch, status=200, capture=None, raise_exc=None):
    def fake_get(url, **kwargs):
        if capture is not None:
            capture["url"] = url
            capture.update(kwargs)
        if raise_exc is not None:
            raise raise_exc
        return SimpleNamespace(status_code=status)

    monkeypatch.setattr("httpx.get", fake_get)


def _patch_post(monkeypatch, status=200, capture=None, raise_exc=None):
    def fake_post(url, **kwargs):
        if capture is not None:
            capture["url"] = url
            capture.update(kwargs)
        if raise_exc is not None:
            raise raise_exc
        return SimpleNamespace(status_code=status)

    monkeypatch.setattr("httpx.post", fake_post)


def test_verify_openai_ok(monkeypatch):
    cap: dict = {}
    _patch_get(monkeypatch, status=200, capture=cap)
    assert verify_provider_key("openai", api_key="sk-x") == {"ok": True}
    assert cap["url"] == "https://api.openai.com/v1/models"
    assert cap["headers"]["Authorization"] == "Bearer sk-x"


def test_verify_openai_custom_endpoint(monkeypatch):
    cap: dict = {}
    _patch_get(monkeypatch, status=200, capture=cap)
    verify_provider_key(
        "openai", api_key="sk-x", base_url="https://gw.example/openai/v1/"
    )
    # trailing slash trimmed, /models appended to the custom endpoint
    assert cap["url"] == "https://gw.example/openai/v1/models"


def test_verify_bad_key_is_invalid(monkeypatch):
    _patch_get(monkeypatch, status=401)
    assert verify_provider_key("openai", api_key="sk-bad") == {
        "ok": False,
        "error": "Invalid API key.",
    }


def test_verify_anthropic_headers(monkeypatch):
    cap: dict = {}
    _patch_get(monkeypatch, status=200, capture=cap)
    verify_provider_key("anthropic", api_key="sk-ant-x")
    assert cap["url"] == "https://api.anthropic.com/v1/models"
    assert cap["headers"]["x-api-key"] == "sk-ant-x"
    assert "anthropic-version" in cap["headers"]


def test_verify_gemini_key_param(monkeypatch):
    cap: dict = {}
    _patch_get(monkeypatch, status=200, capture=cap)
    verify_provider_key("gemini", api_key="AIza-x")
    assert cap["params"]["key"] == "AIza-x"


def test_verify_ollama_uses_v1_models_no_key(monkeypatch):
    cap: dict = {}
    _patch_get(monkeypatch, status=200, capture=cap)
    verify_provider_key("ollama", base_url="http://localhost:11434")
    assert cap["url"] == "http://localhost:11434/v1/models"
    assert "headers" not in cap  # keyless


@pytest.mark.parametrize(
    "name,base_url,model",
    [
        (
            "ark",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
            "dola-seed-evolving-latest-version",
        ),
        (
            "ark-agent-plan-cn",
            "https://ark.cn-beijing.volces.com/api/plan/v3",
            "doubao-seed-evolving",
        ),
    ],
)
def test_verify_ark_uses_non_persisted_responses_probe(
    monkeypatch, name, base_url, model
):
    """Reverse-verified probe: the captured fixture must be non-empty and provider-specific."""
    cap: dict = {}
    _patch_post(monkeypatch, status=200, capture=cap)

    assert verify_provider_key(name, api_key="ark-key") == {"ok": True}
    assert cap["url"] == base_url + "/responses"
    assert cap["headers"]["Authorization"] == "Bearer ark-key"
    assert cap["json"] == {
        "model": model,
        "input": "Reply with OK.",
        "max_output_tokens": 1,
        "store": False,
    }


def test_verify_ark_profile_endpoint_override(monkeypatch):
    cap: dict = {}
    _patch_post(monkeypatch, status=200, capture=cap)

    verify_provider_key(
        "ark",
        api_key="ark-key",
        base_url="https://gateway.example/ark/v3/",
    )

    assert cap["url"] == "https://gateway.example/ark/v3/responses"


@pytest.mark.parametrize("base_url", [None, "https://proxy.example/coding/v3/"])
def test_verify_coding_plan_uses_chat_inference(monkeypatch, base_url):
    cap: dict = {}
    _patch_post(monkeypatch, capture=cap)
    assert verify_provider_key(
        "ark-coding-plan-cn", api_key="coding-key", base_url=base_url
    ) == {"ok": True}
    expected = (base_url or "https://ark.cn-beijing.volces.com/api/coding/v3").rstrip("/")
    assert cap["url"] == expected + "/chat/completions"
    assert cap["headers"]["Authorization"] == "Bearer coding-key"
    assert cap["json"] == {
        "model": "ark-code-latest",
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "max_tokens": 1,
    }


def test_coding_plan_settings_save_reload_and_remove(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from coworker.server import SessionManager, create_app

    manager = SessionManager(data_dir=tmp_path)
    client = TestClient(create_app(manager))
    name = "ark-coding-plan-cn"
    rows = {p["name"]: p for p in client.get("/v1/providers").json()}
    assert rows[name]["suggested_models"] == ["ark-code-latest"]
    assert not rows[name]["configured"]
    cap: dict = {}
    _patch_post(monkeypatch, status=401, capture=cap)
    body = {"name": name, "fields": {"api_key": "coding-key"}}
    assert not client.post("/v1/providers/verify", json=body).json()["ok"]
    _patch_post(monkeypatch, capture=cap)
    assert client.post("/v1/providers/verify", json=body).json()["ok"]
    assert cap["url"] == "https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions"
    assert cap["headers"]["Authorization"] == "Bearer coding-key"
    assert not manager.secrets.get(f"provider:{name}")  # Testing never saves.
    for provider, key in [("ark-agent-plan-cn", "agent-key"), (name, "coding-key")]:
        assert client.post("/v1/providers", json={
            "name": provider, "fields": {"api_key": key},
        }).json()["ok"]

    reloaded = SessionManager(data_dir=tmp_path)
    rows = {p["name"]: p for p in reloaded.get_providers()}
    assert rows[name]["configured"]
    assert "api_key" not in rows[name]["values"]
    assert reloaded.secrets.get(f"provider:{name}")["api_key"] == "coding-key"
    assert f"{name}:ark-code-latest" in client.get("/v1/settings").json()["models"]
    assert client.delete(f"/v1/providers/{name}").json()["ok"]
    assert manager.secrets.get("provider:ark-agent-plan-cn")["api_key"] == "agent-key"
    rows = {p["name"]: p for p in client.get("/v1/providers").json()}
    assert not rows[name]["configured"]


def test_verify_network_error_is_clean(monkeypatch):
    _patch_get(monkeypatch, raise_exc=ConnectionError("boom"))
    res = verify_provider_key("openai", api_key="sk-x")
    assert res["ok"] is False
    assert "Couldn't reach" in res["error"]


def test_verify_unexpected_status(monkeypatch):
    _patch_get(monkeypatch, status=500)
    res = verify_provider_key("anthropic", api_key="sk-ant-x")
    assert res["ok"] is False
    assert "500" in res["error"]
