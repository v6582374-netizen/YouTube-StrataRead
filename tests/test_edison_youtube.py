"""The imported host, its model router and the retained library meet at this seam."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app, youtube
from youtube_strataread.downloader.youtube import SubtitleResult
from youtube_strataread.workbench.discovery import Candidate


class Provider(ProviderClient):
    def __init__(self):
        self.calls = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls.append((model, messages, tools))
        return AssistantTurn(text="# 中文稿件\n\n由主客户端模型生成。")

    def capabilities(self, model):
        return ModelCapabilities()


def test_youtube_uses_the_hosts_current_model_without_legacy_configuration():
    provider = Provider()
    manager = SimpleNamespace(
        model="first-model",
        provider_complete=lambda m, msgs, tools: provider.complete(
            model=m, messages=msgs, tools=tools
        ),
    )
    generator = youtube.HostManuscripts(manager)
    assert generator.generate("Timed source") == "# 中文稿件\n\n由主客户端模型生成。"
    manager.model = "second-model"
    generator.generate("Second source")
    assert [c[0] for c in provider.calls] == ["first-model", "second-model"]
    assert provider.calls[0][1][-1]["content"] == "Timed source"
    assert provider.calls[0][2] is None


def test_authenticated_host_library_waits_for_model_then_prepares_and_hands_off(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("YOUTUBE_WORKBENCH_WORKSPACE", str(tmp_path / "youtube"))
    monkeypatch.setenv("COWORKER_API_TOKEN", "fixture-token")
    monkeypatch.setattr(youtube.YouTubeWorkbench, "_run", lambda self: None)
    provider = Provider()
    manager = SessionManager(data_dir=tmp_path / "host", provider=provider, model="host-model")
    ready = {"model_ready": False}
    monkeypatch.setattr(manager, "get_settings", lambda: ready)
    app = create_app(manager)
    with TestClient(app) as client:
        assert (
            client.post("/v1/youtube/capability", json={"capability": "library.list"}).status_code
            == 401
        )
        client.headers["X-OpenWorker-Token"] = "fixture-token"

        def request(capability, **arguments):
            response = client.post(
                "/v1/youtube/capability", json={"capability": capability, "arguments": arguments}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"], data
            return data["result"]

        assert request("library.list")["total"] == 0
        service = app.state.youtube
        service.workspace.add_candidate(
            Candidate(
                "fixture",
                "channel",
                "Channel",
                "Title",
                "https://www.youtube.com/watch?v=fixture",
                "2026-09-18",
                1_789_728_000,
            )
        )
        service.preparation.captions = SimpleNamespace(
            acquire=lambda url: SubtitleResult(
                "fixture", "Title", "en", False, "1\n00:00:00,000 --> 00:00:02,000\nSource\n"
            )
        )
        assert not service.prepare_one()
        assert request("library.list")["assets"][0]["preparation_state"] == "queued"
        assert not provider.calls
        ready["model_ready"] = True
        assert service.prepare_one()
        assert provider.calls[0][0] == "host-model"
        assert request("activity.snapshot")["model"] == "host-model"
        assert request("library.list")["assets"][0]["preparation_state"] == "ready"
        assert request("documents.get", video_id="fixture")["markdown"].startswith("# 中文稿件")
        request("library.set_reading_state", video_id="fixture", reading_state="to-read")
        assert request("library.list", reading_state="to-read")["total"] == 1
        assert request("library.inspect", video_id="fixture")["source_trace"][
            "transcript_available"
        ]
        request("library.delete", video_id="fixture")
        assert request("library.list")["total"] == 0


def test_model_failures_do_not_leak_provider_details():
    def fail(*args, **kwargs):
        raise RuntimeError("Bearer fixture-secret")

    import pytest

    with pytest.raises(RuntimeError, match="Edison") as error:
        youtube.HostManuscripts(SimpleNamespace(model="model", provider_complete=fail)).generate(
            "source"
        )
    assert "fixture-secret" not in str(error.value)


def test_shutdown_during_discovery_cannot_start_a_new_asset(tmp_path, monkeypatch):
    import threading

    entered, release = threading.Event(), threading.Event()
    monkeypatch.setenv("YOUTUBE_WORKBENCH_WORKSPACE", str(tmp_path))

    def discover(self):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(youtube.SubscriptionDiscovery, "refresh", discover)
    calls = []
    monkeypatch.setattr(youtube.YtDlpCaptions, "acquire", lambda self, url: calls.append(url))
    manager = SimpleNamespace(get_settings=lambda: {"model_ready": True})
    service = youtube.YouTubeWorkbench(manager)
    service.workspace.add_candidate(
        Candidate(
            "one",
            "channel",
            "Channel",
            "Title",
            "https://www.youtube.com/watch?v=one",
            "2026-09-18",
            1_789_728_000,
        )
    )
    try:
        assert entered.wait(3)
        service.close()
    finally:
        release.set()
        service.thread.join(3)
    assert not calls
    assert service.workspace.asset("one")["preparation_state"] == "queued"


def test_channel_exclusion_and_prompt_survive_restart_without_removing_documents(
    tmp_path, monkeypatch
):
    from youtube_strataread.workbench.connection import SubscriptionSource
    from youtube_strataread.workbench.workspace import LocalWorkspace

    monkeypatch.setenv("YOUTUBE_WORKBENCH_WORKSPACE", str(tmp_path / "youtube"))
    monkeypatch.setattr(youtube.YouTubeWorkbench, "_run", lambda self: None)
    provider = Provider()
    manager = SimpleNamespace(
        model="host-model",
        get_settings=lambda: {"model_ready": True},
        provider_complete=lambda m, msgs, tools: provider.complete(
            model=m, messages=msgs, tools=tools
        ),
    )
    service = youtube.YouTubeWorkbench(manager)
    try:
        ws = service.workspace
        ws.replace_subscription_sources(
            [SubscriptionSource("a", "A"), SubscriptionSource("b", "B")]
        )
        assert service.dispatch("collection.preferences", {})["result"]["excluded_channels"] == []
        for id in ["ready", "waiting"]:
            ws.add_candidate(
                Candidate(
                    id,
                    "a",
                    "A",
                    id,
                    "https://www.youtube.com/watch?v=" + id,
                    "2026-09-18",
                    1789728000,
                )
            )
        service.preparation.captions = SimpleNamespace(
            acquire=lambda url: SubtitleResult(
                "ready", "Title", "en", False, "1\n00:00:00,000 --> 00:00:02,000\nSource\n"
            )
        )
        assert service.prepare_one()
        original = service.library.document("ready")["markdown"]
        assert service.dispatch("collection.set_exclusions", {"excluded_channels": ["a"]})["ok"]
        assert not service.prepare_one()
        assert service.library.document("ready")["markdown"] == original
        ws.replace_subscription_sources(
            [
                SubscriptionSource("a", "A"),
                SubscriptionSource("b", "B"),
                SubscriptionSource("new", "New"),
            ]
        )
        assert service.dispatch("collection.preferences", {})["result"]["excluded_channels"] == [
            "a"
        ]
        assert not ws.add_candidate(
            Candidate(
                "blocked",
                "a",
                "A",
                "Blocked",
                "https://www.youtube.com/watch?v=blocked",
                "2026-09-18",
                1789728000,
            )
        )
        assert service.dispatch(
            "generation.set_prompt", {"prompt": "使用简体中文，不添加原文以外的事实。"}
        )["ok"]
        reopened = LocalWorkspace.open(ws.root)
        youtube.HostManuscripts(manager, reopened).generate("next source")
        assert provider.calls[-1][1][0]["content"] == "使用简体中文，不添加原文以外的事实。"
        assert reopened.excluded_channels() == ["a"]
        assert service.library.document("ready")["markdown"] == original
        assert not service.dispatch("generation.set_prompt", {"prompt": " "})["ok"]
        assert not service.dispatch("collection.set_exclusions", {"excluded_channels": "a"})["ok"]
        assert service.dispatch("library.list", {"documents_only": True})["result"]["total"] == 1
    finally:
        service.close()
