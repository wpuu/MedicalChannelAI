"""Bounded public-page transport; not connected to any production collector.

An isolated, short-lived child does only HTTP reads. Killing/reaping it bounds
DNS/TLS/slow-read work without process-global alarms in the parent. Deployment
support for spawning/cleaning this child still needs runtime verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.message import Message
from html.parser import HTMLParser
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SOURCE_INDEXES = {
    "tjzyefy": "https://www.tjzyefy.com/xwgg/ggtz/",
    "tjzyefy_intent": "https://www.tjzyefy.com/xwgg/ggtz/",
    "tjzxfc": "https://www.tjzxfc.cn/ywgk/zbgg/index.shtml",
}
SOURCE_HOSTS = {
    "tjzyefy": frozenset({"www.tjzyefy.com", "tjzyefy.com"}),
    "tjzyefy_intent": frozenset({"www.tjzyefy.com", "tjzyefy.com"}),
    "tjzxfc": frozenset({"www.tjzxfc.cn", "tjzxfc.cn"}),
}
MAX_PAGE_BYTES = 1024 * 1024
REQUEST_SECONDS = 20.0
WORK_SECONDS = 240.0
MIN_GAP_SECONDS = 3.0
CLEANUP_SECONDS = 2.0
RETRYABLE_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
CHARSET_SCAN_BYTES = 8192
_CHARSETS = {"utf-8": "utf-8", "utf8": "utf-8", "gb2312": "gb2312",
             "gb_2312-80": "gb2312", "gbk": "gbk", "gb18030": "gb18030"}


class OfficialFetchError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.retryable = retryable


@dataclass(frozen=True)
class OfficialPage:
    stage: str
    url: str
    html: str
    html_sha256: str
    observed_at: datetime


def _charset_name(value) -> str:
    if not isinstance(value, str) or value.strip().lower() not in _CHARSETS:
        raise OfficialFetchError("OFFICIAL_CHARSET_REJECTED")
    return _CHARSETS[value.strip().lower()]


def _header_charset(headers) -> str | None:
    if len(headers.get_all("Content-Type", [])) > 1:
        raise OfficialFetchError("OFFICIAL_CHARSET_REJECTED")
    values = [value for key, value in (headers.get_params() or []) if key.lower() == "charset"]
    if len(values) > 1:
        raise OfficialFetchError("OFFICIAL_CHARSET_REJECTED")
    return _charset_name(values[0]) if values else None


class _HTMLCharsets(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = []
        self.ended = False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.ended = True
        if self.ended or tag != "meta":
            return
        attributes = dict(attrs)
        if len(attributes) != len(attrs):
            raise OfficialFetchError("OFFICIAL_CHARSET_REJECTED")
        if "charset" in attributes:
            self.values.append(_charset_name(attributes["charset"]))
        if (attributes.get("http-equiv") or "").strip().lower() == "content-type":
            content = attributes.get("content")
            if not isinstance(content, str):
                raise OfficialFetchError("OFFICIAL_CHARSET_REJECTED")
            header = Message()
            header["Content-Type"] = content
            value = _header_charset(header)
            if value:
                self.values.append(value)

    def handle_endtag(self, tag):
        if tag == "head":
            self.ended = True


def _decode_official_html(body: bytes, headers) -> str:
    """Only bounded head declarations; no guessed codecs or replacement text."""
    declared = _HTMLCharsets()
    # Latin-1 preserves ASCII markup while inspecting undecoded response bytes.
    declared.feed(body[:CHARSET_SCAN_BYTES].decode("latin-1"))
    declared.close()
    values = set(declared.values)
    header = _header_charset(headers)
    if header:
        values.add(header)
    bom = body.startswith(b"\xef\xbb\xbf")
    if bom:
        values.add("utf-8")
    if len(values) > 1:
        raise OfficialFetchError("OFFICIAL_CHARSET_CONFLICT")
    charset = next(iter(values), "utf-8")
    try:
        return body.decode("utf-8-sig" if bom else charset)
    except UnicodeError as exc:
        raise OfficialFetchError("OFFICIAL_PAGE_DECODE_FAILED") from exc


def validate_official_url(stage: str, url: str) -> str:
    try:
        if stage not in SOURCE_INDEXES or not isinstance(url, str) or len(url) > 2048:
            raise ValueError()
        if any(ord(char) <= 32 or ord(char) == 127 for char in url):
            raise ValueError()
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in SOURCE_HOSTS[stage]
                or parsed.username or parsed.password or parsed.port not in {None, 443}
                or parsed.query or parsed.fragment):
            raise ValueError()
        index_path = urlsplit(SOURCE_INDEXES[stage]).path
        identity = re.fullmatch(r"/system/(20\d{2})/(\d{2})/(\d{2})/(\d+)\.shtml", parsed.path)
        if parsed.path != index_path:
            if not identity:
                raise ValueError()
            date(*(int(value) for value in identity.groups()[:3]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise OfficialFetchError("OFFICIAL_URL_REJECTED") from exc
    return url


class _OfficialRedirects(HTTPRedirectHandler):
    max_redirections = 3

    def __init__(self, stage: str):
        self.stage = stage
        self._redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_official_url(self.stage, newurl)
        self._redirect_count += 1
        if self._redirect_count > 3:
            raise OfficialFetchError("OFFICIAL_REDIRECT_LIMIT")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _worker_fetch(stage: str, url: str, deadline: float) -> dict:
    """Called only inside the bounded child; no cache, Queue or secrets API."""
    validate_official_url(stage, url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True)
    request = Request(url, headers={
        "User-Agent": "MedicalChannelAI/0.1 official-public-evidence",
        "Accept": "text/html,application/xhtml+xml", "Accept-Encoding": "identity",
    })
    try:
        with build_opener(_OfficialRedirects(stage)).open(request, timeout=remaining) as response:
            validate_official_url(stage, response.geturl())
            if response.status != 200:
                raise OfficialFetchError("OFFICIAL_HTTP_REJECTED")
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                raise OfficialFetchError("OFFICIAL_CONTENT_TYPE_REJECTED")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise OfficialFetchError("OFFICIAL_CONTENT_ENCODING_REJECTED")
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdigit() or len(length) > 12 or int(length) > MAX_PAGE_BYTES):
                raise OfficialFetchError("OFFICIAL_PAGE_TOO_LARGE")
            body = response.read(MAX_PAGE_BYTES + 1)
            if len(body) > MAX_PAGE_BYTES:
                raise OfficialFetchError("OFFICIAL_PAGE_TOO_LARGE")
            html = _decode_official_html(body, response.headers)
            if not html.strip():
                raise OfficialFetchError("OFFICIAL_PAGE_EMPTY")
            return {"html": html, "url": response.geturl(), "observed_at": datetime.now(timezone.utc).isoformat()}
    except HTTPError as exc:
        raise OfficialFetchError(f"OFFICIAL_HTTP_{exc.code}", retryable=exc.code in RETRYABLE_HTTP) from exc
    except URLError as exc:
        retryable = not isinstance(exc.reason, ssl.SSLCertVerificationError)
        raise OfficialFetchError("OFFICIAL_NETWORK_ERROR", retryable=retryable) from exc
    except TimeoutError as exc:
        raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True) from exc


def _run_bounded_worker(command: list[str], deadline: float) -> bytes:
    """Private fixed-command runner; never accepts commands from HTTP input."""
    if type(deadline) not in {int, float} or not math.isfinite(deadline) or deadline <= time.monotonic():
        raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True)
    # Only TLS trust configuration is inherited. Public reads need no app tokens.
    env = {name: os.environ[name] for name in ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR") if name in os.environ}
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=env, close_fds=True)
    except OSError as exc:
        raise OfficialFetchError("OFFICIAL_WORKER_UNAVAILABLE") from exc
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True)
        try:
            stdout, _ = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True) from exc
        if time.monotonic() >= deadline:
            raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True)
        if process.returncode == -getattr(signal, "SIGALRM", 14):
            raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True)
        if process.returncode != 0 or len(stdout) > MAX_PAGE_BYTES * 8 + 4096:
            raise OfficialFetchError("OFFICIAL_WORKER_FAILED")
        return stdout
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except OSError as exc:
                raise OfficialFetchError("OFFICIAL_WORKER_CLEANUP_FAILED") from exc
            try:
                process.communicate(timeout=CLEANUP_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise OfficialFetchError("OFFICIAL_WORKER_CLEANUP_FAILED") from exc


def fetch_official_page(stage: str, url: str, *, deadline: float) -> OfficialPage:
    validate_official_url(stage, url)
    if type(deadline) not in {int, float} or not math.isfinite(deadline):
        raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE")
    request_deadline = min(deadline, time.monotonic() + REQUEST_SECONDS)
    stdout = _run_bounded_worker([
        sys.executable, "-I", str(Path(__file__).resolve()), "--fetch", stage, url, str(request_deadline),
    ], request_deadline)
    try:
        result = json.loads(stdout)
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise ValueError()
        if not result["ok"]:
            codes = {"OFFICIAL_NETWORK_ERROR", "OFFICIAL_REQUEST_DEADLINE", "OFFICIAL_URL_REJECTED",
                     "OFFICIAL_WORKER_UNAVAILABLE", "OFFICIAL_WORKER_RESULT_INVALID", "OFFICIAL_REDIRECT_LIMIT",
                     "OFFICIAL_HTTP_REJECTED", "OFFICIAL_CONTENT_TYPE_REJECTED", "OFFICIAL_CONTENT_ENCODING_REJECTED",
                     "OFFICIAL_PAGE_TOO_LARGE", "OFFICIAL_CHARSET_REJECTED", "OFFICIAL_CHARSET_CONFLICT",
                     "OFFICIAL_PAGE_DECODE_FAILED", "OFFICIAL_PAGE_EMPTY"}
            code = result.get("error")
            if code not in codes and not (isinstance(code, str) and re.fullmatch(r"OFFICIAL_HTTP_[1-5]\d\d", code)):
                raise ValueError()
            raise OfficialFetchError(code, retryable=result.get("retryable") is True)
        html, final_url = result["html"], result["url"]
        validate_official_url(stage, final_url)
        if not isinstance(html, str) or not html.strip() or len(html.encode("utf-8")) > MAX_PAGE_BYTES * 4:
            raise ValueError()
        observed = datetime.fromisoformat(result["observed_at"])
        if observed.tzinfo is None or observed > datetime.now(timezone.utc):
            raise ValueError()
    except (ValueError, KeyError, TypeError) as exc:
        raise OfficialFetchError("OFFICIAL_WORKER_RESULT_INVALID") from exc
    return OfficialPage(stage, final_url, html, hashlib.sha256(html.encode("utf-8")).hexdigest(), observed)


class OfficialFetchSession:
    """One source's shared index/detail/retry budget; not a persistent cursor."""
    def __init__(self, stage: str):
        if stage not in SOURCE_INDEXES:
            raise OfficialFetchError("OFFICIAL_URL_REJECTED")
        self.stage = stage
        self.deadline = time.monotonic() + WORK_SECONDS
        self._last_request_end: float | None = None

    def fetch(self, url: str) -> OfficialPage:
        validate_official_url(self.stage, url)
        for attempt in range(2):
            if self._last_request_end is not None:
                gap = max(0.0, MIN_GAP_SECONDS - (time.monotonic() - self._last_request_end))
                if time.monotonic() + gap >= self.deadline:
                    raise OfficialFetchError("OFFICIAL_SOURCE_BUDGET_EXHAUSTED")
                if gap:
                    time.sleep(gap)
            if time.monotonic() >= self.deadline:
                raise OfficialFetchError("OFFICIAL_SOURCE_BUDGET_EXHAUSTED")
            try:
                page = fetch_official_page(self.stage, url, deadline=self.deadline)
            except OfficialFetchError as exc:
                if attempt == 1 or not exc.retryable:
                    raise
            else:
                if time.monotonic() >= self.deadline:
                    raise OfficialFetchError("OFFICIAL_SOURCE_BUDGET_EXHAUSTED")
                return page
            finally:
                self._last_request_end = time.monotonic()
        raise AssertionError("unreachable")


def _worker_main() -> int:
    if len(sys.argv) != 5 or sys.argv[1] != "--fetch":
        return 2
    try:
        deadline = float(sys.argv[4])
        remaining = deadline - time.monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise OfficialFetchError("OFFICIAL_REQUEST_DEADLINE", retryable=True)
        # This alarm belongs only to this dedicated child, never the handler.
        if not hasattr(signal, "setitimer"):
            raise OfficialFetchError("OFFICIAL_WORKER_UNAVAILABLE")
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        result = {"ok": True, **_worker_fetch(sys.argv[2], sys.argv[3], deadline)}
    except OfficialFetchError as exc:
        result = {"ok": False, "error": str(exc), "retryable": exc.retryable}
    except Exception:
        result = {"ok": False, "error": "OFFICIAL_WORKER_RESULT_INVALID", "retryable": False}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_worker_main())
