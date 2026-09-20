"""Session authentication for the local Coven service."""

from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
import hmac
import secrets
import time
from typing import Mapping


SESSION_COOKIE = "coven_session"


@dataclass(frozen=True)
class Session:
    id: str
    created_at: float


class AuthManager:
    def __init__(self, *, bootstrap_token: str | None = None):
        self.bootstrap_token = bootstrap_token or secrets.token_urlsafe(24)
        self._bootstrap_used = False
        self._sessions: dict[str, Session] = {}

    @property
    def bootstrap_used(self) -> bool:
        return self._bootstrap_used

    def create_session(self, token: str) -> str:
        if self._bootstrap_used:
            raise PermissionError("Bootstrap token has already been used.")
        if not hmac.compare_digest(token, self.bootstrap_token):
            raise PermissionError("Invalid bootstrap token.")
        self._bootstrap_used = True
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = Session(id=session_id, created_at=time.time())
        return session_id

    def is_valid_cookie(self, cookie_header: str | None) -> bool:
        session_id = self.session_from_cookie(cookie_header)
        return session_id in self._sessions

    def session_from_cookie(self, cookie_header: str | None) -> str | None:
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except Exception:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        if morsel is None:
            return None
        return morsel.value

    def cookie_header(self, session_id: str) -> str:
        return f"{SESSION_COOKIE}={session_id}; HttpOnly; SameSite=Strict; Path=/"


def parse_host(host_header: str | None) -> tuple[str, int | None]:
    if not host_header:
        return "", None
    value = host_header.strip()
    if value.startswith("["):
        host, _, rest = value[1:].partition("]")
        port = None
        if rest.startswith(":"):
            try:
                port = int(rest[1:])
            except ValueError:
                port = None
        return host.lower(), port
    if value.count(":") == 1:
        host, port_text = value.rsplit(":", 1)
        try:
            return host.lower(), int(port_text)
        except ValueError:
            return host.lower(), None
    return value.lower(), None


def is_allowed_origin(
    *,
    host_header: str | None,
    origin_header: str | None,
    allowed_hosts: set[str],
    server_port: int,
) -> bool:
    host, port = parse_host(host_header)
    if host not in allowed_hosts or (port is not None and port != server_port):
        return False
    if not origin_header:
        return True
    from urllib.parse import urlparse

    parsed = urlparse(origin_header)
    origin_host = (parsed.hostname or "").lower()
    origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return origin_host in allowed_hosts and origin_port == server_port and parsed.scheme in {"http", "https"}


def has_write_intent(headers: Mapping[str, str]) -> bool:
    return headers.get("X-Coven-Intent") == "ui-action"
