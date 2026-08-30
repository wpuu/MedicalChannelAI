from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from typing import Callable, Type

from .outreach_client import AgnesOutreachClient
from .pilot_api import CanonicalOriginPolicy, dispatch_pilot_api
from .today_runtime import SQLiteTodayRuntime, build_sqlite_today_runtime


MAX_REQUEST_BODY_BYTES = 64 * 1024
OUTREACH_API_KEY_ENV = "MCAI_AGNES_API_KEY"
OUTREACH_BASE_URL_ENV = "MCAI_AGNES_BASE_URL"
CANONICAL_ORIGIN_ENV = "MCAI_CANONICAL_ORIGIN"


def build_outreach_model_call_from_env(
    environ: dict[str, str] | None = None,
) -> Callable[[dict], dict] | None:
    """Build the server-only outreach provider from process environment.

    Absence of the key is allowed so the rest of the Pilot can run without outreach.
    The raw key is never returned, logged or persisted. Base URL remains subject to
    the Agnes official-host allowlist enforced by AgnesOutreachClient.
    """

    env = os.environ if environ is None else environ
    api_key = (env.get(OUTREACH_API_KEY_ENV) or "").strip()
    if not api_key:
        return None
    base_url = (env.get(OUTREACH_BASE_URL_ENV) or "").strip()
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AgnesOutreachClient(**kwargs)


def build_origin_policy_from_env(
    environ: dict[str, str] | None = None,
) -> CanonicalOriginPolicy:
    """Require one canonical HTTPS origin for the authenticated real Pilot."""

    env = os.environ if environ is None else environ
    value = (env.get(CANONICAL_ORIGIN_ENV) or "").strip()
    if not value:
        raise ValueError(f"{CANONICAL_ORIGIN_ENV} is required")
    return CanonicalOriginPolicy.parse(value)


def build_handler(
    runtime: SQLiteTodayRuntime,
    origin_policy: CanonicalOriginPolicy | None = None,
) -> Type[BaseHTTPRequestHandler]:
    """Build the HTTP adapter.

    origin_policy remains optional only for isolated unit-level adapter use.
    serve() always supplies a required policy from MCAI_CANONICAL_ORIGIN.
    """

    class PilotHandler(BaseHTTPRequestHandler):
        server_version = "MedicalChannelAI"
        sys_version = ""

        def _handle(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return
            if content_length < 0 or content_length > MAX_REQUEST_BODY_BYTES:
                self.send_error(413)
                return
            body = self.rfile.read(content_length) if content_length else b""
            response = dispatch_pilot_api(
                runtime,
                method=self.command,
                target=self.path,
                headers={key: value for key, value in self.headers.items()},
                body=body,
                now=datetime.now(timezone.utc),
                origin_policy=origin_policy,
            )
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_PATCH(self) -> None:
            self._handle()

        def do_DELETE(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

    return PilotHandler


def serve(*, db_path: Path, host: str = "127.0.0.1", port: int = 8787) -> None:
    if not isinstance(port, int) or isinstance(port, bool) or port < 1 or port > 65535:
        raise ValueError("port must be 1..65535")
    origin_policy = build_origin_policy_from_env()
    runtime = build_sqlite_today_runtime(
        Path(db_path),
        outreach_model_call=build_outreach_model_call_from_env(),
    )
    server = ThreadingHTTPServer((host, port), build_handler(runtime, origin_policy))
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="MedicalChannelAI single-host Pilot API")
    parser.add_argument("--db", required=True, type=Path, help="persistent Pilot SQLite path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()
    serve(db_path=args.db, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
