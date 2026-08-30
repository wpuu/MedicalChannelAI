from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class HealthHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def json_body(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8"))


_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def handle_health_request(*, method: str, target: str, body: bytes) -> HealthHttpResponse:
    parsed = urlsplit(target)
    if parsed.path != "/healthz" or parsed.query or parsed.fragment:
        payload = {"error": "NOT_FOUND"}
        code = 404
    elif method.upper() != "GET" or body:
        payload = {"error": "METHOD_NOT_ALLOWED" if method.upper() != "GET" else "INVALID_REQUEST"}
        code = 405 if method.upper() != "GET" else 400
    else:
        payload = {
            "schema_version": "0.1",
            "status": "ok",
            "mode": "SINGLE_HOST_PILOT",
        }
        code = 200
    return HealthHttpResponse(
        status_code=code,
        headers=dict(_HEADERS),
        body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )
