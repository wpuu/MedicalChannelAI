from __future__ import annotations

import hashlib
import importlib.metadata
import io
from dataclasses import dataclass
from typing import Any, Iterable

from .attachment_parser import (
    AttachmentParseError,
    AttachmentTextBlock,
    MAX_TEXT_CHARS,
    ParsedAttachmentText,
)
from .attachments import AttachmentSnapshot


PARSER_VERSION = "pdf-docling-v0.1"
MAX_PDF_PAGES = 200
MAX_PDF_BYTES = 32 * 1024 * 1024
MAX_PDF_BLOCKS = 50_000


@dataclass(frozen=True)
class PdfParserRuntime:
    backend: str
    backend_version: str
    remote_services_enabled: bool
    max_pages: int
    max_bytes: int

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "backend_version": self.backend_version,
            "remote_services_enabled": self.remote_services_enabled,
            "max_pages": self.max_pages,
            "max_bytes": self.max_bytes,
        }


def _verify_pdf_snapshot(snapshot: AttachmentSnapshot) -> None:
    digest = hashlib.sha256(snapshot.body).hexdigest()
    if digest != snapshot.sha256:
        raise AttachmentParseError(
            "SNAPSHOT_HASH_MISMATCH",
            "PDF bytes no longer match attachment snapshot SHA-256",
        )
    if snapshot.extension != ".pdf":
        raise AttachmentParseError(
            "PDF_EXTENSION_REQUIRED",
            f"Docling PDF parser received {snapshot.extension}",
        )
    if not snapshot.body:
        raise AttachmentParseError("EMPTY_ATTACHMENT", "PDF attachment body is empty")
    if len(snapshot.body) > MAX_PDF_BYTES:
        raise AttachmentParseError(
            "PDF_TOO_LARGE",
            f"PDF exceeds {MAX_PDF_BYTES} bytes",
        )
    if not snapshot.body.lstrip().startswith(b"%PDF-"):
        raise AttachmentParseError(
            "INVALID_PDF_SIGNATURE",
            "attachment does not begin with a PDF signature",
        )


def _serialize_bbox(bbox: Any) -> dict | None:
    if bbox is None:
        return None
    values = {}
    for key in ("l", "t", "r", "b"):
        value = getattr(bbox, key, None)
        if value is None:
            return None
        values[key] = float(value)
    origin = getattr(bbox, "coord_origin", None)
    if origin is not None:
        values["coord_origin"] = getattr(origin, "value", str(origin))
    return values


def _serialize_charspan(charspan: Any) -> list[int] | None:
    if charspan is None:
        return None
    try:
        values = list(charspan)
    except TypeError:
        return None
    if len(values) != 2:
        return None
    try:
        return [int(values[0]), int(values[1])]
    except (TypeError, ValueError):
        return None


def _serialize_provenance(item: Any) -> list[dict]:
    result: list[dict] = []
    for prov in getattr(item, "prov", ()) or ():
        page_no = getattr(prov, "page_no", None)
        bbox = _serialize_bbox(getattr(prov, "bbox", None))
        charspan = _serialize_charspan(getattr(prov, "charspan", None))
        if page_no is None or bbox is None:
            continue
        record = {
            "page_no": int(page_no),
            "bbox": bbox,
        }
        if charspan is not None:
            record["charspan"] = charspan
        result.append(record)
    return result


def _item_text(item: Any, document: Any) -> tuple[str | None, str]:
    text = getattr(item, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip(), "PDF_TEXT"

    export_table = getattr(item, "export_to_markdown", None)
    if callable(export_table):
        try:
            rendered = export_table(doc=document)
        except TypeError:
            rendered = export_table(document)
        if isinstance(rendered, str) and rendered.strip():
            return rendered.strip(), "PDF_TABLE"
    return None, "PDF_OTHER"


def extract_grounded_docling_blocks(document: Any) -> tuple[AttachmentTextBlock, ...]:
    """Convert a DoclingDocument-like object into evidence-grounded blocks.

    Only items carrying page+bbox provenance are emitted. Text without source
    geometry is intentionally dropped so downstream facts cannot cite an
    ungrounded parser output as official evidence.
    """

    iterator = getattr(document, "iterate_items", None)
    if not callable(iterator):
        raise AttachmentParseError(
            "DOCLING_DOCUMENT_API_UNSUPPORTED",
            "Docling document does not expose iterate_items()",
        )

    blocks: list[AttachmentTextBlock] = []
    total_chars = 0
    for entry in iterator(with_groups=False):
        item = entry[0] if isinstance(entry, tuple) else entry
        text, kind = _item_text(item, document)
        if not text:
            continue
        provenance = _serialize_provenance(item)
        if not provenance:
            continue
        total_chars += len(text)
        if total_chars > MAX_TEXT_CHARS:
            raise AttachmentParseError(
                "PARSED_TEXT_TOO_LARGE",
                f"Docling PDF text exceeds {MAX_TEXT_CHARS} characters",
            )
        blocks.append(
            AttachmentTextBlock(
                kind=kind,
                locator={
                    "self_ref": getattr(item, "self_ref", None),
                    "provenance": provenance,
                },
                text=text,
            )
        )
        if len(blocks) > MAX_PDF_BLOCKS:
            raise AttachmentParseError(
                "PDF_TOO_MANY_BLOCKS",
                f"Docling PDF exceeds {MAX_PDF_BLOCKS} grounded blocks",
            )
    return tuple(blocks)


def parse_pdf_with_docling(snapshot: AttachmentSnapshot) -> tuple[ParsedAttachmentText, PdfParserRuntime]:
    _verify_pdf_snapshot(snapshot)

    try:
        from docling.datamodel.base_models import DocumentStream, InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise AttachmentParseError(
            "DOCLING_NOT_INSTALLED",
            "optional PDF backend requires the docling package",
        ) from exc

    try:
        backend_version = importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        backend_version = "unknown"

    # Remote services stay disabled. Docling can use local OCR/layout/table models;
    # model artifacts should be pre-provisioned by the deployment environment.
    pipeline_options = PdfPipelineOptions(
        do_table_structure=True,
        do_ocr=True,
        enable_remote_services=False,
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
    )
    stream = DocumentStream(name=snapshot.filename, stream=io.BytesIO(snapshot.body))
    try:
        conversion = converter.convert(
            stream,
            raises_on_error=True,
            max_num_pages=MAX_PDF_PAGES,
            max_file_size=MAX_PDF_BYTES,
        )
    except Exception as exc:  # backend-specific exceptions stay behind one fail-closed boundary
        raise AttachmentParseError(
            "DOCLING_CONVERSION_FAILED",
            f"Docling failed to convert PDF: {type(exc).__name__}: {exc}",
        ) from exc

    document = getattr(conversion, "document", None)
    if document is None:
        raise AttachmentParseError(
            "DOCLING_DOCUMENT_MISSING",
            "Docling conversion returned no document",
        )

    pages = getattr(document, "pages", None)
    if pages is not None and len(pages) > MAX_PDF_PAGES:
        raise AttachmentParseError(
            "PDF_TOO_MANY_PAGES",
            f"Docling document exceeds {MAX_PDF_PAGES} pages",
        )

    blocks = extract_grounded_docling_blocks(document)
    if not blocks:
        raise AttachmentParseError(
            "PDF_NO_GROUNDED_TEXT",
            "Docling produced no text/table blocks carrying page+bbox provenance",
        )

    parsed = ParsedAttachmentText(
        attachment_id=snapshot.attachment_id,
        source_url=snapshot.source_url,
        filename=snapshot.filename,
        extension=snapshot.extension,
        snapshot_sha256=snapshot.sha256,
        parser_version=f"{PARSER_VERSION}/docling-{backend_version}",
        blocks=blocks,
        total_text_chars=sum(len(block.text) for block in blocks),
    )
    runtime = PdfParserRuntime(
        backend="docling",
        backend_version=backend_version,
        remote_services_enabled=False,
        max_pages=MAX_PDF_PAGES,
        max_bytes=MAX_PDF_BYTES,
    )
    return parsed, runtime
