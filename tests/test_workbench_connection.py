from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from youtube_strataread.workbench.connection import (
    ConnectionService,
    OAuthClientConfiguration,
    OAuthCredentials,
    SubscriptionSource,
)
from youtube_strataread.workbench.workspace import LocalWorkspace


@dataclass
class MemoryVault:
    values: dict[str, str]

    def save(self, key: str, value: str) -> None:
        self.values[key] = value

    def load(self, key: str) -> str | None:
        return self.values.get(key)


@dataclass
class FakeGoogleOAuth:
    subscriptions: list[SubscriptionSource]

    def authorize(self, configuration: OAuthClientConfiguration) -> OAuthCredentials:
        assert configuration.client_id == "desktop-client"
        return OAuthCredentials(access_token="short-lived", refresh_token="long-lived")

    def list_subscriptions(self, credentials: OAuthCredentials) -> list[SubscriptionSource]:
        assert credentials.access_token == "short-lived"
        return self.subscriptions


def test_connection_configuration_and_authorization_imports_subscription_sources(
    tmp_path: Path,
) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    vault = MemoryVault(values={})
    service = ConnectionService(
        workspace=workspace,
        vault=vault,
        oauth=FakeGoogleOAuth(
            subscriptions=[
                SubscriptionSource(channel_id="alpha", title="Alpha"),
                SubscriptionSource(channel_id="beta", title="Beta"),
            ]
        ),
    )

    configured = service.configure(client_id="desktop-client", client_secret="not-a-real-secret")
    connected = service.authorize_and_import()
    disconnected = service.disconnect()

    assert configured.as_result() == {
        "configured": True,
        "authorized": False,
        "subscription_count": 0,
    }
    assert connected.as_result() == {
        "configured": True,
        "authorized": True,
        "subscription_count": 2,
    }
    assert disconnected.as_result() == {
        "configured": True,
        "authorized": False,
        "subscription_count": 2,
    }
    assert [source["title"] for source in workspace.subscription_sources()] == ["Alpha", "Beta"]
    assert "not-a-real-secret" not in str(connected.as_result())
