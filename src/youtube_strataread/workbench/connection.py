"""User-owned Google OAuth and YouTube subscription-source behavior."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from youtube_strataread.workbench.vault import SecretVault, VaultError
from youtube_strataread.workbench.workspace import LocalWorkspace

_CLIENT_ID = "YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID"
_CLIENT_SECRET = "YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET"
_ACCESS_TOKEN = "YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN"
_REFRESH_TOKEN = "YOUTUBE_WORKBENCH_OAUTH_REFRESH_TOKEN"
_EXPIRES_AT = "YOUTUBE_WORKBENCH_OAUTH_EXPIRES_AT"
_YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


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
    expires_at: float | None = None


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

    def refresh(
        self,
        configuration: OAuthClientConfiguration,
        refresh_token: str,
    ) -> OAuthCredentials: ...

    def list_subscriptions(self, credentials: OAuthCredentials) -> list[SubscriptionSource]: ...


class GoogleOAuthGateway:
    """Small standard-library client for a user-owned Google desktop OAuth client."""

    def authorize(self, configuration: OAuthClientConfiguration) -> OAuthCredentials:
        callback = _CallbackServer()
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
            .decode("ascii")
            .rstrip("=")
        )
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
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                }
            )
            if not webbrowser.open(f"https://accounts.google.com/o/oauth2/v2/auth?{query}"):
                raise ConnectionError("Could not open a browser for Google authorization")
            code, returned_state, provider_error = callback.wait()
            if provider_error:
                raise ConnectionError("Google authorization was not completed")
            if returned_state != state or not code:
                raise ConnectionError("Google authorization callback could not be verified")
            return self._exchange(
                {
                    "code": code,
                    "client_id": configuration.client_id,
                    "client_secret": configuration.client_secret,
                    "redirect_uri": callback.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                }
            )
        finally:
            callback.close()

    def refresh(
        self,
        configuration: OAuthClientConfiguration,
        refresh_token: str,
    ) -> OAuthCredentials:
        refreshed = self._exchange(
            {
                "client_id": configuration.client_id,
                "client_secret": configuration.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )
        return OAuthCredentials(
            access_token=refreshed.access_token,
            refresh_token=refreshed.refresh_token or refresh_token,
            expires_at=refreshed.expires_at,
        )

    def list_subscriptions(self, credentials: OAuthCredentials) -> list[SubscriptionSource]:
        sources: list[SubscriptionSource] = []
        page_token: str | None = None
        seen_page_tokens: set[str] = set()
        seen_channel_ids: set[str] = set()
        while True:
            query: dict[str, str] = {
                "part": "snippet",
                "mine": "true",
                "maxResults": "50",
            }
            if page_token:
                if page_token in seen_page_tokens:
                    raise ConnectionError("YouTube subscriptions response repeated a page token")
                seen_page_tokens.add(page_token)
                query["pageToken"] = page_token
            request = Request(
                f"https://www.googleapis.com/youtube/v3/subscriptions?{urlencode(query)}",
                headers={"Authorization": f"Bearer {credentials.access_token}"},
            )
            try:
                with urlopen(request, timeout=30) as response:
                    payload: object = json.load(response)
            except (OSError, json.JSONDecodeError) as error:
                raise ConnectionError("YouTube subscriptions could not be imported") from error
            if not isinstance(payload, dict):
                raise ConnectionError("YouTube subscriptions response was invalid")
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise ConnectionError("YouTube subscriptions response was invalid")
            for item in items:
                if not isinstance(item, dict):
                    continue
                snippet = item.get("snippet", {})
                if not isinstance(snippet, dict):
                    continue
                resource = snippet.get("resourceId", {})
                if not isinstance(resource, dict):
                    continue
                channel_value = resource.get("channelId")
                if not isinstance(channel_value, str) or not channel_value.strip():
                    continue
                channel_id = channel_value.strip()
                if channel_id in seen_channel_ids:
                    continue
                seen_channel_ids.add(channel_id)
                thumbnails = snippet.get("thumbnails", {})
                default_thumbnail = (
                    thumbnails.get("default", {}) if isinstance(thumbnails, dict) else {}
                )
                sources.append(
                    SubscriptionSource(
                        channel_id=channel_id,
                        title=str(snippet.get("title") or channel_id),
                        description=str(snippet.get("description") or ""),
                        thumbnail_url=(
                            str(default_thumbnail.get("url") or "")
                            if isinstance(default_thumbnail, dict)
                            else ""
                        )
                        or None,
                        subscribed_at=str(snippet.get("publishedAt") or "") or None,
                    )
                )
            page_token = str(payload.get("nextPageToken") or "") or None
            if not page_token:
                return sources

    def _exchange(self, values: dict[str, str]) -> OAuthCredentials:
        response = _post_form(_TOKEN_ENDPOINT, values)
        access_token = str(response.get("access_token") or "")
        if not access_token:
            raise ConnectionError("Google authorization did not return an access token")
        expires_in = response.get("expires_in")
        expires_at = (
            time.time() + float(expires_in) if isinstance(expires_in, int | float) else None
        )
        return OAuthCredentials(
            access_token=access_token,
            refresh_token=str(response.get("refresh_token") or "") or None,
            expires_at=expires_at,
        )


class ConnectionService:
    """Owns connection state while keeping credential values outside workspace data."""

    def __init__(
        self, *, workspace: LocalWorkspace, vault: SecretVault, oauth: GoogleOAuth
    ) -> None:
        self.workspace = workspace
        self.vault = vault
        self.oauth = oauth

    def status(self) -> ConnectionStatus:
        try:
            configuration = self._configuration()
            access_token = self.vault.load(_ACCESS_TOKEN)
            refresh_token = self.vault.load(_REFRESH_TOKEN)
        except VaultError as error:
            raise ConnectionError("Automic Vault is unavailable") from error
        return ConnectionStatus(
            configured=configuration is not None,
            authorized=bool(access_token or (configuration and refresh_token)),
            subscription_count=self.workspace.subscription_source_count(),
        )

    def configure(self, *, client_id: str, client_secret: str) -> ConnectionStatus:
        if not client_id.strip() or not client_secret.strip():
            raise ConnectionError("Google OAuth client ID and secret are required")
        try:
            self.vault.save(_CLIENT_ID, client_id.strip())
            self.vault.save(_CLIENT_SECRET, client_secret.strip())
        except VaultError as error:
            raise ConnectionError("Automic Vault could not save the Google OAuth client") from error
        return self.status()

    def authorize_and_import(self) -> ConnectionStatus:
        configuration = self._require_configuration()
        credentials = self.oauth.authorize(configuration)
        self._store_credentials(credentials)
        self.workspace.replace_subscription_sources(self.oauth.list_subscriptions(credentials))
        return self.status()

    def refresh_subscription_sources(self) -> ConnectionStatus:
        credentials = self._active_credentials()
        self.workspace.replace_subscription_sources(self.oauth.list_subscriptions(credentials))
        return self.status()

    def subscription_sources(self) -> list[dict[str, str | None]]:
        return self.workspace.subscription_sources()

    def disconnect(self) -> ConnectionStatus:
        try:
            self.vault.save(_ACCESS_TOKEN, "")
            self.vault.save(_REFRESH_TOKEN, "")
            self.vault.save(_EXPIRES_AT, "")
        except VaultError as error:
            raise ConnectionError(
                "Automic Vault could not clear the YouTube authorization"
            ) from error
        return self.status()

    def _active_credentials(self) -> OAuthCredentials:
        configuration = self._require_configuration()
        try:
            access_token = self.vault.load(_ACCESS_TOKEN)
            refresh_token = self.vault.load(_REFRESH_TOKEN)
            expires_at = _float_or_none(self.vault.load(_EXPIRES_AT))
        except VaultError as error:
            raise ConnectionError("Automic Vault is unavailable") from error
        if not access_token or (expires_at is not None and expires_at <= time.time() + 60):
            if not refresh_token:
                raise ConnectionError("YouTube authorization expired; reconnect the account")
            credentials = self.oauth.refresh(configuration, refresh_token)
            self._store_credentials(credentials)
            return credentials
        return OAuthCredentials(
            access_token=access_token, refresh_token=refresh_token, expires_at=expires_at
        )

    def _store_credentials(self, credentials: OAuthCredentials) -> None:
        try:
            self.vault.save(_ACCESS_TOKEN, credentials.access_token)
            self.vault.save(_REFRESH_TOKEN, credentials.refresh_token or "")
            self.vault.save(_EXPIRES_AT, str(credentials.expires_at or ""))
        except VaultError as error:
            raise ConnectionError(
                "Automic Vault could not store the YouTube authorization"
            ) from error

    def _require_configuration(self) -> OAuthClientConfiguration:
        configuration = self._configuration()
        if configuration is None:
            raise ConnectionError("Configure a Google OAuth client before connecting YouTube")
        return configuration

    def _configuration(self) -> OAuthClientConfiguration | None:
        try:
            client_id = self.vault.load(_CLIENT_ID)
            client_secret = self.vault.load(_CLIENT_SECRET)
        except VaultError as error:
            raise ConnectionError("Automic Vault is unavailable") from error
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
                if urlparse(self.path).path != "/oauth/callback":
                    self.send_error(404)
                    return
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


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _post_form(url: str, values: dict[str, str]) -> dict[str, object]:
    request = Request(url, data=urlencode(values).encode("utf-8"), method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            payload: object = json.load(response)
    except (OSError, json.JSONDecodeError) as error:
        raise ConnectionError("Google authorization token exchange failed") from error
    if not isinstance(payload, dict):
        raise ConnectionError("Google authorization token response was invalid")
    return {str(key): value for key, value in payload.items()}
