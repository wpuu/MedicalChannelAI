from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import uuid
from pathlib import Path

from .attachment_parser import AttachmentParseError, parse_attachment
from .attachments import AttachmentSnapshot
from .collector_core import ID_NAMESPACE, utc_now_iso
from .pdf_parser_docling import parse_pdf_with_docling


LOCAL_PARSE_EXTENSIONS = {".docx", ".xlsx"}
PDF_EXTENSION = ".pdf"
MAX_LOCAL_FILE_BYTES = 32 * 1024 * 1024


def snapshot_from_local_file(path: Path, source_url: str) -> AttachmentSnapshot:
    body = path.read_bytes()
    if not body:
        raise AttachmentParseError("EMPTY_ATTACHMENT", "local attachment file is empty")
    if len(body) > MAX_LOCAL_FILE_BYTES:
        raise AttachmentParseError(
            "ATTACHMENT_TOO_LARGE",
            f"local attachment exceeds {MAX_LOCAL_FILE_BYTES} bytes",
        )
    extension = path.suffix.lower()
    if extension not in LOCAL_PARSE_EXTENSIONS | {PDF_EXTENSION}:
        raise AttachmentParseError(
            "VALIDATION_EXTENSION_NOT_SUPPORTED",
            f"local validation CLI supports DOCX/XLSX/PDF, got {extension}",
        )
    digest = hashlib.sha256(body).hexdigest()
    attachment_uuid = uuid.uuid5(ID_NAMESPACE, f"attachment|{source_url}|{digest}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return AttachmentSnapshot(
        attachment_id=f"att_{attachment_uuid}",
        source_url=source_url,
        filename=path.name,
        extension=extension,
        fetched_at=utc_now_iso(),
        status_code=200,
        content_type=content_type,
        size_bytes=len(body),
        sha256=digest,
        body=body,
        parser_eligible=extension in LOCAL_PARSE_EXTENSIONS,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate already-captured official procurement attachment bytes without network access."
    )
    parser.add_argument("file", type=Path, help="Local official attachment file")
    parser.add_argument("--source-url", required=True, help="Official attachment source URL recorded by the collector")
    parser.add_argument(
        "--enable-docling-pdf",
        action="store_true",
        help="Explicitly enable the optional local Docling PDF backend. Remote Docling services remain disabled.",
    )
    args = parser.parse_args()

    try:
        snapshot = snapshot_from_local_file(args.file, args.source_url)
        runtime = None
        if snapshot.extension in LOCAL_PARSE_EXTENSIONS:
            parsed = parse_attachment(snapshot)
        elif snapshot.extension == PDF_EXTENSION:
            if not args.enable_docling_pdf:
                raise AttachmentParseError(
                    "PDF_BACKEND_NOT_ENABLED",
                    "PDF validation requires explicit --enable-docling-pdf",
                )
            parsed, runtime = parse_pdf_with_docling(snapshot)
        else:  # guarded by snapshot_from_local_file
            raise AttachmentParseError("PARSER_NOT_IMPLEMENTED", snapshot.extension)
    except (OSError, AttachmentParseError) as exc:
        code = getattr(exc, "code", "LOCAL_FILE_ERROR")
        print(
            json.dumps(
                {"status": "ERROR", "code": code, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2

    result = {
        "status": "OK",
        "snapshot": snapshot.metadata(),
        "parsed": parsed.as_dict(),
        "pdf_runtime": runtime.as_dict() if runtime is not None else None,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
