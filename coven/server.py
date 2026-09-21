"""Loopback HTTP server for the Coven workspace."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .adapters import default_data_dir
from .agent_adapters import AdapterError, build_agent_adapter
from .auth import AuthManager, has_write_intent, is_allowed_origin
from .configuration import ConfigError, load_app_config
from .runtime import RuntimeInspector
from .store import CovenStore
from .voice import VoiceService


ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
PROFILE_PATH = ROOT / "config" / "witches.json"
MAX_BODY = 128 * 1024
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "media-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


class CovenHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    store: CovenStore
    auth: AuthManager
    runtime: RuntimeInspector
    namespace: str
    agent_adapter: object
    voice: VoiceService


class CovenHandler(BaseHTTPRequestHandler):
    server_version = "CovenWorkspace/0.2"

    @property
    def app(self) -> CovenHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("[coven] " + format % args + "\n")

    def _send_json(self, payload: object, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(
        self,
        status: int,
        message: str,
        *,
        code: str = "request_error",
        details: object | None = None,
    ) -> None:
        payload: dict[str, object] = {"error": message, "code": code}
        if details is not None:
            payload["details"] = details
        self._send_json(payload, status)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length must be an integer.") from exc
        if length > MAX_BODY:
            raise ValueError("Request body is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Request JSON body must be an object.")
        return payload

    def _check_origin(self) -> bool:
        return is_allowed_origin(
            host_header=self.headers.get("Host"),
            origin_header=self.headers.get("Origin"),
            allowed_hosts=ALLOWED_HOSTS,
            server_port=self.app.server_port,
        )

    def _is_authenticated(self) -> bool:
        return self.app.auth.is_valid_cookie(self.headers.get("Cookie"))

    def _require_auth(self) -> bool:
        if self._is_authenticated():
            return True
        self._send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication is required.", code="auth_required")
        return False

    def do_GET(self) -> None:
        if not self._check_origin():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Host or Origin is not allowed.", code="origin_forbidden")
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json({"ok": True, "service": "coven-workspace"})
        elif path == "/api/auth/status":
            self._send_json({"authenticated": self._is_authenticated(), "bootstrapUsed": self.app.auth.bootstrap_used})
        elif path == "/api/status":
            if self._require_auth():
                self._send_json(self.app.runtime.get())
        elif path == "/api/config":
            if self._require_auth():
                self._send_json({"namespace": self.app.namespace})
        elif path == "/api/profiles":
            if self._require_auth():
                self._send_json({"witches": self.app.store.profiles()})
        elif path == "/api/tasks":
            if self._require_auth():
                scope = self.app.store.snapshot(
                    namespace=self.app.namespace,
                    advance_demo=self.app.namespace == "demo",
                )
                self._send_json({"tasks": scope["tasks"]})
        elif path.startswith("/api/tasks/"):
            if self._require_auth():
                task_id = unquote(path.rsplit("/", 1)[-1])
                scope = self.app.store.snapshot(
                    namespace=self.app.namespace,
                    advance_demo=self.app.namespace == "demo",
                )
                task = next((item for item in scope["tasks"] if item["id"] == task_id), None)
                if task is None:
                    self._send_error_json(HTTPStatus.NOT_FOUND, "Task not found.", code="task_not_found")
                else:
                    self._send_json({"task": task})
        elif path.startswith("/api/conversations/"):
            if self._require_auth():
                witch_id = unquote(path.rsplit("/", 1)[-1])
                self._send_json({"messages": self.app.store.conversations(witch_id, namespace=self.app.namespace)})
        elif path == "/api/failure-events":
            if self._require_auth():
                self.app.store.snapshot(namespace=self.app.namespace, advance_demo=self.app.namespace == "demo")
                self._send_json({"events": self.app.store.pending_failure_events(namespace=self.app.namespace)})
        elif path == "/api/settings":
            if self._require_auth():
                self._send_json({"settings": self.app.store.preferences()})
        elif path == "/api/voice/status":
            if self._require_auth():
                self._send_json({"voice": self.app.voice.status()})
        else:
            self._serve_static(path)

    def do_HEAD(self) -> None:
        if not self._check_origin():
            self.send_response(HTTPStatus.FORBIDDEN)
            self.end_headers()
            return
        self._serve_static(urlparse(self.path).path, send_body=False)

    def do_POST(self) -> None:
        if not self._check_origin():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Host or Origin is not allowed.", code="origin_forbidden")
            return
        if not has_write_intent(self.headers):
            self._send_error_json(HTTPStatus.FORBIDDEN, "Missing write intent header.", code="missing_write_intent")
            return

        parsed = urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json()
            if path == "/api/auth/session":
                token = body.get("token")
                if not isinstance(token, str):
                    raise ValueError("token must be a string.")
                session_id = self.app.auth.create_session(token)
                self._send_json(
                    {"authenticated": True},
                    HTTPStatus.CREATED,
                    headers={"Set-Cookie": self.app.auth.cookie_header(session_id)},
                )
            elif not self._is_authenticated():
                self._send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication is required.", code="auth_required")
            elif path == "/api/status/refresh":
                self._send_json(self.app.runtime.get(force=True))
            elif path.startswith("/api/conversations/"):
                witch_id = unquote(path.rsplit("/", 1)[-1])
                text = body.get("message")
                result = self.app.agent_adapter.send_message(witch_id, text)  # type: ignore[attr-defined]
                self._send_json({"messages": result.messages or [], "witchId": witch_id, "details": result.details}, HTTPStatus.CREATED)
            elif path == "/api/tasks":
                runtime = self.app.runtime.get()
                if self.app.namespace != "demo" and not runtime["hermesApi"]["configured"]:
                    self._send_error_json(
                        HTTPStatus.CONFLICT,
                        "Hermes API transport is not configured. Live task dispatch remains unavailable.",
                        code="hermes_api_unconfigured",
                        details=runtime["hermesApi"],
                    )
                    return
                result = self.app.agent_adapter.create_task(body)  # type: ignore[attr-defined]
                task = result.task
                self._send_json({"task": task}, HTTPStatus.CREATED)
            elif path.startswith("/api/tasks/") and path.endswith("/retry"):
                task_id = unquote(path.split("/")[-2])
                result = self.app.agent_adapter.retry_task(task_id)  # type: ignore[attr-defined]
                self._send_json({"task": result.task}, HTTPStatus.CREATED)
            elif path == "/api/cinematics":
                event_id = body.get("eventId")
                disposition = body.get("disposition")
                if not isinstance(event_id, str) or not event_id:
                    raise ValueError("eventId must be a non-empty string.")
                if not isinstance(disposition, str):
                    raise ValueError("disposition must be a string.")
                self._send_json(
                    {"cinematics": self.app.store.mark_cinematic(event_id, disposition, namespace=self.app.namespace)}
                )
            elif path == "/api/settings":
                self._send_json({"settings": self.app.store.update_preferences(body)})
            else:
                self._send_error_json(HTTPStatus.NOT_FOUND, "Unknown endpoint.", code="not_found")
        except PermissionError as exc:
            self._send_error_json(HTTPStatus.FORBIDDEN, str(exc), code="auth_denied")
        except AdapterError as exc:
            self._send_error_json(HTTPStatus.CONFLICT, str(exc), code=exc.code, details=exc.details)
        except KeyError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "Requested item was not found.", code="not_found")
        except (ValueError, ConfigError, json.JSONDecodeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc), code="bad_request")

    def _serve_static(self, path: str, *, send_body: bool = True) -> None:
        if path in {"/", "/index.html"} and not self._is_authenticated():
            rel = Path("auth.html")
        elif path == "/":
            rel = Path("index.html")
        else:
            rel = Path(unquote(path.lstrip("/")))
        target = (PUBLIC / rel).resolve()
        try:
            target.relative_to(PUBLIC.resolve())
        except ValueError:
            self._send_error_json(HTTPStatus.FORBIDDEN, "Path is not allowed.", code="path_forbidden")
            return
        if not target.exists() or not target.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, "File not found.", code="file_not_found")
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        dynamic_suffixes = {".html", ".css", ".js", ".json"}
        self.send_header("Cache-Control", "no-store" if target.suffix in dynamic_suffixes else "public, max-age=3600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not send_body:
            return
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return


def build_server(
    host: str,
    port: int,
    data_dir: Path,
    *,
    config_path: Path | None = None,
    auth_token: str | None = None,
) -> CovenHTTPServer:
    config = load_app_config(config_path)
    server = CovenHTTPServer((host, port), CovenHandler)
    server.store = CovenStore(data_dir=data_dir, profile_path=PROFILE_PATH)
    server.auth = AuthManager(bootstrap_token=auth_token or os.environ.get("COVEN_DEV_AUTH_TOKEN"))
    server.runtime = RuntimeInspector(config)
    server.namespace = "demo" if config.demo_mode else "live"
    server.agent_adapter = build_agent_adapter(config, server.store)
    server.voice = VoiceService()
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the local Coven workspace.")
    parser.add_argument("--config", type=Path, default=None, help="Optional Coven JSON configuration.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--auth-token", default=None, help="One-time development bootstrap token.")
    parser.add_argument("--open", action="store_true", help="Open the workspace in the default browser.")
    args = parser.parse_args(argv)

    config = load_app_config(args.config)
    host = args.host or config.server.host
    port = args.port or config.server.port
    data_dir = args.data_dir or config.server.data_dir or default_data_dir()

    if host not in ALLOWED_HOSTS:
        parser.error("Coven binds to loopback only.")

    server = build_server(host, port, data_dir, config_path=args.config, auth_token=args.auth_token)
    url = f"http://{host}:{port}/"
    print(f"Coven workspace listening on {url}")
    print(f"Data directory: {data_dir}")
    print("Development browser unlock token:")
    print(server.auth.bootstrap_token)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Coven workspace.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
