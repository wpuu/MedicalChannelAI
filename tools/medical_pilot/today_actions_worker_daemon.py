from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import time

from .agnes_client import AgnesChatClient
from .today_actions_queue_worker import execute_next_queued_today_actions_task
from .today_runtime import build_sqlite_today_runtime


AGNES_API_KEY_ENV = "MCAI_AGNES_API_KEY"
AGNES_BASE_URL_ENV = "MCAI_AGNES_BASE_URL"


def build_agnes_client_from_env(environ: dict[str, str] | None = None) -> AgnesChatClient:
    env = os.environ if environ is None else environ
    api_key = (env.get(AGNES_API_KEY_ENV) or "").strip()
    if not api_key:
        raise ValueError(f"{AGNES_API_KEY_ENV} is required for Today Actions worker")
    base_url = (env.get(AGNES_BASE_URL_ENV) or "").strip()
    kwargs: dict[str, object] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AgnesChatClient(**kwargs)


def _worker_id() -> str:
    host = socket.gethostname().strip() or "medicalai"
    return f"today-actions:{host}:{os.getpid()}"


def run_worker(*, db_path: Path, idle_sleep_seconds: float = 1.0) -> None:
    if idle_sleep_seconds <= 0 or idle_sleep_seconds > 30:
        raise ValueError("idle_sleep_seconds must be within 0..30")

    client = build_agnes_client_from_env()
    runtime = build_sqlite_today_runtime(Path(db_path))
    worker_id = _worker_id()

    while True:
        now = datetime.now(timezone.utc)
        try:
            result = execute_next_queued_today_actions_task(
                queue=runtime.dispatch_queue,
                lease_store=runtime.lease_store,
                result_store=runtime.result_store,
                worker_id=worker_id,
                now=now,
                model_call=client,
            )
            # Never log provider payloads, model output, API keys, tenant data or
            # customer profile fields. Status-only logs are sufficient for systemd.
            print(
                f"today_actions_worker status={result.status} error_code={result.error_code or '-'}",
                flush=True,
            )
            if result.status == "NOT_CLAIMED":
                time.sleep(idle_sleep_seconds)
            elif result.status in {"READY", "MODEL_OUTPUT_REJECTED", "ALREADY_COMPLETED"}:
                # Drain another due item immediately; global lease still enforces
                # provider start spacing and max in-flight limits.
                continue
            else:
                time.sleep(idle_sleep_seconds)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            # Do not serialize exception messages because upstream errors can carry
            # provider/account details. The class is enough for operational triage.
            print(f"today_actions_worker failure={type(exc).__name__}", flush=True)
            time.sleep(min(5.0, max(1.0, idle_sleep_seconds)))


def main() -> None:
    parser = argparse.ArgumentParser(description="MedicalChannelAI Agnes Today Actions worker")
    parser.add_argument("--db", required=True, type=Path, help="persistent Pilot SQLite path")
    parser.add_argument("--idle-sleep", type=float, default=1.0)
    args = parser.parse_args()
    run_worker(db_path=args.db, idle_sleep_seconds=args.idle_sleep)


if __name__ == "__main__":
    main()
