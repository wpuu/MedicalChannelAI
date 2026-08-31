from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .attachment_parser import parse_attachment
from .attachments import AttachmentCandidate, BoundedAttachmentFetcher
from .product_classifier import classify_product_facts
from .registry import TIANJIN_GOVERNMENT_DETAIL_HOSTS


SUPPORTED_LIVE_PROBE_EXTENSIONS = {".docx", ".xlsx"}


class AttachmentLiveProbeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_tianjin_finance_attachment_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise AttachmentLiveProbeError("ATTACHMENT_URL_INVALID", "attachment URL is invalid") from exc

    host = (parsed.hostname or "").lower().strip(".")
    if parsed.scheme != "https":
        raise AttachmentLiveProbeError("ATTACHMENT_HTTPS_REQUIRED", "live attachment probe requires HTTPS")
    if host not in TIANJIN_GOVERNMENT_DETAIL_HOSTS:
        raise AttachmentLiveProbeError("ATTACHMENT_HOST_NOT_ALLOWED", "attachment host is not an approved Tianjin government host")
    if parsed.path != "/portal/documentView.do" or parsed.fragment:
        raise AttachmentLiveProbeError("ATTACHMENT_ROUTE_NOT_ALLOWED", "attachment route is not approved")

    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise AttachmentLiveProbeError("ATTACHMENT_QUERY_INVALID", "attachment query is invalid") from exc

    if set(query) != {"id", "method"} or any(len(values) != 1 for values in query.values()):
        raise AttachmentLiveProbeError("ATTACHMENT_QUERY_NOT_ALLOWED", "attachment query must contain one id and one method only")
    if query["method"][0] != "downEnId" or not query["id"][0].strip():
        raise AttachmentLiveProbeError("ATTACHMENT_ROUTE_NOT_ALLOWED", "attachment route is not an approved downEnId download")


def validate_probe_filename(filename: str) -> str:
    clean = PurePosixPath(filename).name.strip()
    if not clean or clean != filename.strip():
        raise AttachmentLiveProbeError("ATTACHMENT_FILENAME_INVALID", "filename must be a basename only")
    extension = PurePosixPath(clean).suffix.lower()
    if extension not in SUPPORTED_LIVE_PROBE_EXTENSIONS:
        raise AttachmentLiveProbeError(
            "ATTACHMENT_EXTENSION_NOT_SUPPORTED",
            "live parser probe currently supports DOCX and XLSX only",
        )
    return extension


def _classification_facts(parsed: Any) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for index, block in enumerate(parsed.blocks, start=1):
        text = str(block.text).strip()
        if not text:
            continue
        facts.append(
            {
                "fact_id": f"probe_fact_{index}",
                "fact_type": "OFFICIAL_PUBLIC_FACT",
                "verification_status": "VERIFIED",
                "model_generated": False,
                "field_value": text,
            }
        )
    return facts


def probe_attachment(*, url: str, filename: str) -> dict[str, Any]:
    validate_tianjin_finance_attachment_url(url)
    extension = validate_probe_filename(filename)
    candidate = AttachmentCandidate(
        source_url=url,
        filename=filename.strip(),
        extension=extension,
        title=filename.strip(),
        handling_policy="DOWNLOAD_AND_PARSE_APPROVED",
        download_authorized=True,
    )
    snapshot = BoundedAttachmentFetcher(
        TIANJIN_GOVERNMENT_DETAIL_HOSTS,
        timeout_seconds=20,
        max_bytes=32 * 1024 * 1024,
    ).fetch(candidate)
    parsed = parse_attachment(snapshot)
    classification = classify_product_facts(_classification_facts(parsed))

    return {
        "schema_version": "0.1",
        "route_family": "TIANJIN_FINANCE_DOWNENID",
        "source_host": (urlsplit(snapshot.source_url).hostname or "").lower(),
        "filename": snapshot.filename,
        "extension": snapshot.extension,
        "status_code": snapshot.status_code,
        "content_type": snapshot.content_type,
        "size_bytes": snapshot.size_bytes,
        "sha256": snapshot.sha256,
        "parser_version": parsed.parser_version,
        "block_count": len(parsed.blocks),
        "total_text_chars": parsed.total_text_chars,
        "taxonomy_validation_status": classification.validation_status,
        "taxonomy_labels": list(classification.labels),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and parse one approved Tianjin government OOXML attachment without persisting its body."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--filename", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = probe_attachment(url=args.url, filename=args.filename)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
