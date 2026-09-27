from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

import vercel.queue as queue


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        names = sorted(name for name in dir(queue) if not name.startswith("_"))
        payload = {
            "module": "vercel.queue",
            "exports": names,
            "has_asgi_app": hasattr(queue, "asgi_app"),
            "has_accept_and_handle": hasattr(queue, "accept_and_handle"),
            "has_subscribe": hasattr(queue, "subscribe"),
            "has_send": hasattr(queue, "send"),
            "has_topic": hasattr(queue, "Topic"),
            "has_message": hasattr(queue, "Message"),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
