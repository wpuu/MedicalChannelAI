from __future__ import annotations

# Importing the module registers the @subscribe handler before asgi_app() is built.
from collector_queue import collector_worker as _collector_worker  # noqa: F401
from vercel.queue import asgi_app

app = asgi_app()
