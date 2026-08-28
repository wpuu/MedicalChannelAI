from __future__ import annotations

import hashlib
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from .collector_core import FetchError, ID_NAMESPACE, extract_anchors, utc_now_iso


DOWNLOADABLE_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
LOCAL_PARSER_EXTENSIONS = {".docx", ".xlsx"}
ARCHIVE_DISCOVERY_ONLY_EXTENSIONS = {".zip", ".rar", ".7z"}
APPROVED_EXTENSIONS = DOWNLOADABLE_DOCUMENT_EXTENSIONS | ARCHIVE_DISCOVERY_ONLY_EXTENSIONS

EXPECTED_MIME_PREFIXES = {
    ".pdf": ("application/pdf",),
    ".doc": ("application/msword", "application/octet-stream"),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    ),
    ".xls": ("application/vnd.ms-excel", "application/octet-stream"),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    ),
}


@dataclass(frozen=True)
class AttachmentCandidate:
    source_url: str
    filename: str
    extension: str
    title: str
    handling_policy: str


@dataclass(frozen=True)
class AttachmentSnapshot:
    attachment_id: str
    source_url: str
    filename: str
    extension: str
    fetched_at: str
    status_code: int
    content_type: str
    size_bytes: int
    sha256: str
    body: bytes
    parser_eligible: bool

    def metadata(self) -> dict:
        return {
            "attachment_id": self.attachment_id,
            "source_url": self.source_url,
            "filename": self.filename,
            "extension": self.extension,
            "fetched_at": self.fetched_at,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "parser_eligible": self.parser_eligible,
        }


def _filename_from_url(url: str, title: str) -> str:
    path_name = PurePosixPath(urllib.parse.urlparse(url).path).name
    if path_name:
        return urllib.parse.unquote(path_name)
    return title.strip() or "attachment"


def _extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def _handling_policy(extension: str) -> str:
    if extension in ARCHIVE_DISCOVERY_ONLY_EXTENSIONS:
        return "DISCOVER_ONLY_ARCHIVE"
    if extension in LOCAL_PARSER_EXTENSIONS:
        return "DOWNLOAD_AND_PARSE_APPROVED"
    return "DOWNLOAD_ONLY_PARSER_PENDING"


def discover_attachments(raw_html: str, base_url: str) -> list[AttachmentCandidate]:
    result: list[AttachmentCandidate] = []
    seen: set[str] = set()
    for link in extract_anchors(raw_html, base_url):
        filename = _filename_from_url(link.url, link.title)
        extension = _extension(filename)
        if extension not in APPROVED_EXTENSIONS:
            title_extension = _extension(link.title)
            if title_extension in APPROVED_EXTENSIONS:
                filename = link.title.strip()
                extension = title_extension
            else:
                continue
        if link.url in seen:
            continue
        seen.add(link.url)
        result.append(
            AttachmentCandidate(
                source_url=link.url,
                filename=filename,
                extension=extension,
                title=link.title,
                handling_policy=_handling_policy(extension),
            )
        )
    return result


class BoundedAttachmentFetcher:
    def __init__(
        self,
        allowed_hosts: Iterable[str],
        *,
        timeout_seconds: int = 20,
        max_bytes: int = 32 * 1024 * 1024,
        user_agent: str = "MedicalChannelAI/0.1 (+public-data-research)",
    ) -> None:
        self.allowed_hosts = {host.lower().strip(".") for host in allowed_hosts}
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.user_agent = user_agent

    def _validate_url(self, url: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().strip(".")
        if parsed.scheme not in {"http", "https"}:
            raise FetchError("UNSUPPORTED_SCHEME", f"unsupported attachment scheme: {parsed.scheme}")
        if host not in self.allowed_hosts:
            raise FetchError("ATTACHMENT_HOST_NOT_ALLOWED", f"attachment host is not registered: {host}")
        return parsed

    def fetch(self, candidate: AttachmentCandidate) -> AttachmentSnapshot:
        if candidate.extension in ARCHIVE_DISCOVERY_ONLY_EXTENSIONS:
            raise FetchError("ARCHIVE_DOWNLOAD_DISABLED", "archive attachments are discovery-only in Pilot v0.1")
        if candidate.extension not in DOWNLOADABLE_DOCUMENT_EXTENSIONS:
            raise FetchError("ATTACHMENT_TYPE_NOT_ALLOWED", candidate.extension)
        self._validate_url(candidate.source_url)

        request = urllib.request.Request(
            candidate.source_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/octet-stream;q=0.5",
            },
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as exc:
            raise FetchError(f"HTTP_{exc.code}", f"attachment HTTP error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise FetchError("NETWORK_ERROR", f"attachment network error: {exc.reason}") from exc

        final_url = response.geturl()
        self._validate_url(final_url)
        content_type = response.headers.get_content_type().lower()
        body = response.read(self.max_bytes + 1)
        if len(body) > self.max_bytes:
            raise FetchError("ATTACHMENT_TOO_LARGE", f"attachment exceeds {self.max_bytes} bytes")
        if not body:
            raise FetchError("EMPTY_ATTACHMENT", "attachment response is empty")

        allowed_mimes = EXPECTED_MIME_PREFIXES.get(candidate.extension, ())
        guessed_mime, _ = mimetypes.guess_type(candidate.filename)
        if allowed_mimes and content_type not in allowed_mimes:
            raise FetchError(
                "ATTACHMENT_MIME_MISMATCH",
                f"extension {candidate.extension} expected {allowed_mimes}, got {content_type}; guessed {guessed_mime}",
            )

        digest = hashlib.sha256(body).hexdigest()
        attachment_uuid = uuid.uuid5(ID_NAMESPACE, f"attachment|{final_url}|{digest}")
        return AttachmentSnapshot(
            attachment_id=f"att_{attachment_uuid}",
            source_url=final_url,
            filename=candidate.filename,
            extension=candidate.extension,
            fetched_at=utc_now_iso(),
            status_code=int(getattr(response, "status", 200)),
            content_type=content_type,
            size_bytes=len(body),
            sha256=digest,
            body=body,
            parser_eligible=candidate.extension in LOCAL_PARSER_EXTENSIONS,
        )
