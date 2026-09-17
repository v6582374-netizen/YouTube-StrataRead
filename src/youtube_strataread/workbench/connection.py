"""User-owned Google OAuth and YouTube subscription-source behavior."""

from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from typing import Any, Protocol
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from youtube_strataread.workbench.vault import SecretVault
from youtube_strataread.workbench.workspace import LocalWorkspace

_CLIENT_ID = "YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID"
_CLIENT_SECRET = "YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET"
_ACCESS_TOKEN = "YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN"
_REFRESH_TOKEN = "YOUTUBE_WORKBENCH_OAUTH_REFRESH_TOKEN"
_YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"


class ConnectionError(RuntimeError):
    """A safe connection error suitable for the desktop UI."""


@dataclass(frozen=True)
class OAuthClientConfiguration:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class OAuthCredentials:
    access_token: str
    refresh_token: str | None


@dataclass(frozen=True)
class SubscriptionSource:
    channel_id: str
    title: str
    description: str = ""
    thumbnail_url: str | None = None
    subscribed_at: str | None = None


@dataclass(frozen=True)
class ConnectionStatus:
    configured: bool
    authorized: bool
    subscription_count: int

    def as_result(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "authorized": self.authorized,
            "subscription_count": self.subscription_count,
        }


class GoogleOAuth(Protocol):
    def authorize(self, configuration: OAuthClientConfiguration) -> OAuthCredentials: ...

    def list_subscriptions(self, credentials: OAuthCredentials) -> list[SubscriptionSource]: ...


class GoogleOAuthGateway:
    """Small standard-library client for a user-owned Google desktop OAuth client."""

    def authorize(self, configuration: OAuthClientConfiguration) -> OAuthCredentials:
        callback = _CallbackServer()
        state = secrets.token_urlsafe(32)
        try:
            query = urlencode(
                {
                    "client_id": configuration.client_id,
                    "redirect_uri": callback.redirect_uri,
                    "response_type": "code",
                    "scope": _YOUTUBE_SCOPE,
                    "access_type": "offline",
                    "prompt": "consent",
                    "state": state,
                }
            )
            webbrowser.open(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")
            code, returned_state, provider_error = callback.wait()
            if provider_error:
                raise ConnectionError("Google authorization was not completed")
            if returned_state != state or not code:
                raise ConnectionError("Google authorization callback could not be verified")
            token_payload = {
                "code": code,
                "client_id": configuration.client_id,
                "client_secret": configuration.client_secret,
                "redirect_uri": callback.redirect_uri,
                "grant_type": "authorization_code",
            }
            response = _post_form("https://oauth2.googleapis.com/token", token_payload)
            access_token = str(response.get("access_token") or "")
            if not access_token:
                raise ConnectionError("Google authorization did not return an access token")
            refresh_token = str(response.get("refresh_token") or "") or None
            return OAuthCredentials(access_token=access_token, refresh_token=refresh_token)
        finally:
            callback.close()

    def list_subscriptions(self, credentials: OAuthCredentials) -> list[SubscriptionSource]:
        sources: list[SubscriptionSource] = []
        page_token: str | None = None
        while True:
            query: dict[str, str] = {
                "part": "snippet",
                "mine": "true",
                "maxResults": "50",
            }
            if page_token:
                query["pageToken"] = page_token
            request = Request(
                f"https://www.googleapis.com/youtube/v3/subscriptions?{urlencode(query)}",
                headers={"Authorization": f"Bearer {credentials.access_token}"},
            )
            try:
                with urlopen(request, timeout=30) as response:
                    payload: dict[str, Any] = json.load(response)
            except OSError as error:
                raise ConnectionError("YouTube subscriptions could not be imported") from error
            for item in payload.get("items", []):
                snippet = item.get("snippet", {})
                resource = snippet.get("resourceId", {})
                channel_id = str(resource.get("channelId") or "")
                if not channel_id:
                    continue
                thumbnails = snippet.get("thumbnails", {})
                default_thumbnail = thumbnails.get("default", {})
                sources.append(
                    SubscriptionSource(
                        channel_id=channel_id,
                        title=str(snippet.get("title") or channel_id),
                        description=str(snippet.get("description") or ""),
                        thumbnail_url=str(default_thumbnail.get("url") or "") or None,
                        subscribed_at=str(snippet.get("publishedAt") or "") or None,
                    )
                )
            page_token = str(payload.get("nextPageToken") or "") or None
            if not page_token:
                return sources


class ConnectionService:
    """Owns connection state while keeping credential values outside workspace data."""

    def __init__(
        self, *, workspace: LocalWorkspace, vault: SecretVault, oauth: GoogleOAuth
    ) -> None:
        self.workspace = workspace
        self.vault = vault
        self.oauth = oauth

    def status(self) -> ConnectionStatus:
        return ConnectionStatus(
            configured=self._configuration() is not None,
            authorized=bool(self.vault.load(_ACCESS_TOKEN)),
            subscription_count=self.workspace.subscription_source_count(),
        )

    def configure(self, *, client_id: str, client_secret: str) -> ConnectionStatus:
        if not client_id.strip() or not client_secret.strip():
            raise ConnectionError("Google OAuth client ID and secret are required")
        self.vault.save(_CLIENT_ID, client_id.strip())
        self.vault.save(_CLIENT_SECRET, client_secret.strip())
        return self.status()

    def authorize_and_import(self) -> ConnectionStatus:
        configuration = self._configuration()
        if configuration is None:
            raise ConnectionError("Configure a Google OAuth client before connecting YouTube")
        credentials = self.oauth.authorize(configuration)
        self.vault.save(_ACCESS_TOKEN, credentials.access_token)
        self.vault.save(_REFRESH_TOKEN, credentials.refresh_token or "")
        self.workspace.replace_subscription_sources(self.oauth.list_subscriptions(credentials))
        return self.status()

    def disconnect(self) -> ConnectionStatus:
        self.vault.save(_ACCESS_TOKEN, "")
        self.vault.save(_REFRESH_TOKEN, "")
        return self.status()

    def _configuration(self) -> OAuthClientConfiguration | None:
        client_id = self.vault.load(_CLIENT_ID)
        client_secret = self.vault.load(_CLIENT_SECRET)
        if not client_id or not client_secret:
            return None
        return OAuthClientConfiguration(client_id=client_id, client_secret=client_secret)


class _CallbackServer:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._query: dict[str, list[str]] = {}
        server = HTTPServer(("127.0.0.1", 0), self._handler())
        self._server = server
        self.redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth/callback"
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

    def wait(self) -> tuple[str | None, str | None, str | None]:
        if not self._event.wait(timeout=300):
            raise ConnectionError("Google authorization timed out")
        return (
            _first(self._query, "code"),
            _first(self._query, "state"),
            _first(self._query, "error"),
        )

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer._query = parse_qs(urlparse(self.path).query)
                outer._event.set()
                body = "YouTube is connected. You can return to 视频资料库."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body.encode("utf-8"))))
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, format: str, *args: object) -> None:
                return

        return CallbackHandler


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key, [])
    return values[0] if values else None


def _post_form(url: str, values: dict[str, str]) -> dict[str, object]:
    request = Request(url, data=urlencode(values).encode("utf-8"), method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            payload: object = json.load(response)
    except OSError as error:
        raise ConnectionError("Google authorization token exchange failed") from error
    if not isinstance(payload, dict):
        raise ConnectionError("Google authorization token response was invalid")
    return {str(key): value for key, value in payload.items()}
