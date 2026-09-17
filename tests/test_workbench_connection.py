from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

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
        assert credentials.access_token in {"short-lived", "refreshed-token"}
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


def test_expired_credentials_refresh_before_subscription_import(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    vault = MemoryVault(
        values={
            "YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID": "desktop-client",
            "YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET": "not-a-real-secret",
            "YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN": "expired-token",
            "YOUTUBE_WORKBENCH_OAUTH_REFRESH_TOKEN": "refresh-token",
            "YOUTUBE_WORKBENCH_OAUTH_EXPIRES_AT": "0",
        }
    )
    oauth = RefreshingGoogleOAuth(
        subscriptions=[SubscriptionSource(channel_id="alpha", title="Alpha")]
    )
    service = ConnectionService(workspace=workspace, vault=vault, oauth=oauth)

    status = service.refresh_subscription_sources()

    assert status.as_result() == {
        "configured": True,
        "authorized": True,
        "subscription_count": 1,
    }
    assert oauth.refreshed is True
    assert vault.values["YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN"] == "refreshed-token"


@dataclass
class RefreshingGoogleOAuth(FakeGoogleOAuth):
    refreshed: bool = False

    def refresh(
        self,
        configuration: OAuthClientConfiguration,
        refresh_token: str,
    ) -> OAuthCredentials:
        assert configuration.client_id == "desktop-client"
        assert refresh_token == "refresh-token"
        self.refreshed = True
        return OAuthCredentials(
            access_token="refreshed-token",
            refresh_token=refresh_token,
            expires_at=2_000_000_000,
        )


@dataclass
class BrokenVault:
    def save(self, key: str, value: str) -> None:
        raise AssertionError("save should not be called")

    def load(self, key: str) -> str | None:
        from youtube_strataread.workbench.vault import VaultError

        raise VaultError("vault unavailable")


def test_vault_unavailability_becomes_a_safe_connection_error(tmp_path: Path) -> None:
    from youtube_strataread.workbench.connection import ConnectionError

    service = ConnectionService(
        workspace=LocalWorkspace.open(tmp_path / "workspace"),
        vault=BrokenVault(),
        oauth=FakeGoogleOAuth(subscriptions=[]),
    )

    with pytest.raises(ConnectionError, match="Automic Vault is unavailable"):
        service.status()


def test_invalid_youtube_response_shape_becomes_a_safe_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from io import BytesIO

    from youtube_strataread.workbench.connection import ConnectionError, GoogleOAuthGateway

    class InvalidResponse:
        def __enter__(self) -> BytesIO:
            return BytesIO(b'{"items": null}')

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
            return False

    monkeypatch.setattr(
        "youtube_strataread.workbench.connection.urlopen",
        lambda *args, **kwargs: InvalidResponse(),
    )

    with pytest.raises(ConnectionError, match="response was invalid"):
        GoogleOAuthGateway().list_subscriptions(
            OAuthCredentials(access_token="not-a-real-token", refresh_token=None)
        )


def test_repeated_subscription_page_token_becomes_a_safe_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from io import BytesIO

    from youtube_strataread.workbench.connection import ConnectionError, GoogleOAuthGateway

    payloads = iter(
        [b'{"items": [], "nextPageToken": "again"}', b'{"items": [], "nextPageToken": "again"}']
    )

    class RepeatedResponse:
        def __enter__(self) -> BytesIO:
            return BytesIO(next(payloads))

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
            return False

    monkeypatch.setattr(
        "youtube_strataread.workbench.connection.urlopen",
        lambda *args, **kwargs: RepeatedResponse(),
    )

    with pytest.raises(ConnectionError, match="repeated a page token"):
        GoogleOAuthGateway().list_subscriptions(
            OAuthCredentials(access_token="not-a-real-token", refresh_token=None)
        )


def test_duplicate_subscription_channel_ids_are_imported_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from io import BytesIO

    from youtube_strataread.workbench.connection import GoogleOAuthGateway

    payload = b'{"items": [{"snippet": {"resourceId": {"channelId": "alpha"}, "title": "Alpha"}}, {"snippet": {"resourceId": {"channelId": "alpha"}, "title": "Alpha duplicate"}}]}'

    class DuplicateResponse:
        def __enter__(self) -> BytesIO:
            return BytesIO(payload)

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
            return False

    monkeypatch.setattr(
        "youtube_strataread.workbench.connection.urlopen",
        lambda *args, **kwargs: DuplicateResponse(),
    )

    sources = GoogleOAuthGateway().list_subscriptions(
        OAuthCredentials(access_token="not-a-real-token", refresh_token=None)
    )

    assert [source.channel_id for source in sources] == ["alpha"]


def test_refresh_token_without_access_token_recovers_subscription_import(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    vault = MemoryVault(
        values={
            "YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID": "desktop-client",
            "YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET": "not-a-real-secret",
            "YOUTUBE_WORKBENCH_OAUTH_REFRESH_TOKEN": "refresh-token",
        }
    )
    oauth = RefreshingGoogleOAuth(
        subscriptions=[SubscriptionSource(channel_id="alpha", title="Alpha")]
    )

    status = ConnectionService(
        workspace=workspace, vault=vault, oauth=oauth
    ).refresh_subscription_sources()

    assert status.authorized is True
    assert oauth.refreshed is True
