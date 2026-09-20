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
from urllib.parse import unquote, urlparse

from .adapters import default_data_dir, inspect_runtime
from .store import CovenStore


ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
PROFILE_PATH = ROOT / "config" / "witches.json"
MAX_BODY = 128 * 1024


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


class CovenHandler(BaseHTTPRequestHandler):
    server_version = "CovenWorkspace/0.1"

    @property
    def store(self) -> CovenStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("[coven] " + format % args + "\n")

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str, details: object | None = None) -> None:
        payload: dict[str, object] = {"error": message}
        if details is not None:
            payload["details"] = details
        self._send_json(payload, status)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            raise ValueError("Request body is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _check_origin(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                return False
        return True

    def _require_write_intent(self) -> bool:
        return self.headers.get("X-Coven-Intent") == "ui-action"

    def do_GET(self) -> None:
        if not self._check_origin():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Host or Origin is not allowed.")
            return

        parsed = urlparse(self.path)
        path = parsed.path
        runtime = inspect_runtime()
        demo_mode = bool(runtime["demoMode"])

        if path == "/api/health":
            self._send_json({"ok": True, "service": "coven-workspace"})
        elif path == "/api/status":
            self._send_json(runtime)
        elif path == "/api/profiles":
            self._send_json({"witches": self.store.profiles()})
        elif path == "/api/tasks":
            state = self.store.snapshot(demo_mode=demo_mode)
            self._send_json({"tasks": state["tasks"]})
        elif path.startswith("/api/tasks/"):
            task_id = unquote(path.rsplit("/", 1)[-1])
            state = self.store.snapshot(demo_mode=demo_mode)
            task = next((item for item in state["tasks"] if item["id"] == task_id), None)
            if task is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "Task not found.")
            else:
                self._send_json({"task": task})
        elif path.startswith("/api/conversations/"):
            witch_id = unquote(path.rsplit("/", 1)[-1])
            self._send_json({"messages": self.store.conversations(witch_id)})
        elif path == "/api/failure-events":
            self.store.snapshot(demo_mode=demo_mode)
            self._send_json({"events": self.store.pending_failure_events()})
        else:
            self._serve_static(path)

    def do_POST(self) -> None:
        if not self._check_origin():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Host or Origin is not allowed.")
            return
        if not self._require_write_intent():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Missing write intent header.")
            return

        parsed = urlparse(self.path)
        path = parsed.path
        runtime = inspect_runtime()
        demo_mode = bool(runtime["demoMode"])

        try:
            body = self._read_json()
            if path.startswith("/api/conversations/"):
                witch_id = unquote(path.rsplit("/", 1)[-1])
                text = str(body.get("message") or "")
                self.store.append_message(witch_id, "user", text)
                reply = self._local_reply(witch_id, demo_mode, runtime)
                messages = self.store.append_message(witch_id, witch_id, reply)
                self._send_json({"messages": messages}, HTTPStatus.CREATED)
            elif path == "/api/tasks":
                if not demo_mode:
                    if not runtime["hermes"]["available"]:
                        self._send_error_json(
                            HTTPStatus.CONFLICT,
                            "Hermes is not available. Task dispatch is disabled outside explicit demo mode.",
                            runtime["hermes"],
                        )
                        return
                    self._send_error_json(
                        HTTPStatus.NOT_IMPLEMENTED,
                        "The live Hermes adapter boundary is present, but dispatch is not implemented in this starter.",
                    )
                    return
                task = self.store.create_task(
                    assignee=str(body.get("assignee") or "morgana"),
                    title=str(body.get("title") or ""),
                    instructions=str(body.get("instructions") or ""),
                    priority=str(body.get("priority") or "normal"),
                )
                self._send_json({"task": task}, HTTPStatus.CREATED)
            elif path.startswith("/api/tasks/") and path.endswith("/retry"):
                task_id = unquote(path.split("/")[-2])
                if not demo_mode:
                    self._send_error_json(HTTPStatus.CONFLICT, "Retry is available only in explicit demo mode.")
                    return
                self._send_json({"task": self.store.retry_task(task_id)}, HTTPStatus.CREATED)
            elif path == "/api/cinematics":
                event_id = str(body.get("eventId") or "")
                disposition = str(body.get("disposition") or "")
                self._send_json({"cinematics": self.store.mark_cinematic(event_id, disposition)})
            else:
                self._send_error_json(HTTPStatus.NOT_FOUND, "Unknown endpoint.")
        except KeyError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "Requested item was not found.")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def _local_reply(self, witch_id: str, demo_mode: bool, runtime: dict[str, object]) -> str:
        if demo_mode:
            return (
                "I recorded this in the durable transcript. Use Assign task when you want a tracked demo quest; "
                "include the word fail to exercise the terminal-failure fixture."
            )
        if not runtime["hermes"]["available"]:  # type: ignore[index]
            return (
                "I recorded the message locally, but Hermes is not installed on PATH, so I cannot dispatch live work yet."
            )
        return "I recorded the message locally. Live Hermes chat transport is documented as an integration gap."

    def _serve_static(self, path: str) -> None:
        if path == "/":
            rel = Path("index.html")
        else:
            rel = Path(unquote(path.lstrip("/")))
        target = (PUBLIC / rel).resolve()
        try:
            target.relative_to(PUBLIC.resolve())
        except ValueError:
            self._send_error_json(HTTPStatus.FORBIDDEN, "Path is not allowed.")
            return
        if not target.exists() or not target.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, "File not found.")
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store" if target.suffix == ".html" else "public, max-age=3600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_server(host: str, port: int, data_dir: Path) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), CovenHandler)
    server.store = CovenStore(data_dir=data_dir, profile_path=PROFILE_PATH)  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the local Coven workspace.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("COVEN_PORT", "8765")))
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--open", action="store_true", help="Open the workspace in the default browser.")
    args = parser.parse_args(argv)

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Coven binds to loopback only.")

    server = build_server(args.host, args.port, args.data_dir)
    url = f"http://{args.host}:{args.port}/"
    print(f"Coven workspace listening on {url}")
    print(f"Data directory: {args.data_dir}")
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
