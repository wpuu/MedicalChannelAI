from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .attachments import AttachmentSnapshot


PARSER_VERSION = "ooxml-stdlib-v0.1"
SUPPORTED_EXTENSIONS = {".docx", ".xlsx"}
MAX_ARCHIVE_MEMBERS = 512
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_TEXT_CHARS = 4 * 1024 * 1024
MAX_XLSX_CELLS = 200_000


class AttachmentParseError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AttachmentTextBlock:
    kind: str
    locator: dict
    text: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "locator": self.locator, "text": self.text}


@dataclass(frozen=True)
class ParsedAttachmentText:
    attachment_id: str
    source_url: str
    filename: str
    extension: str
    snapshot_sha256: str
    parser_version: str
    blocks: tuple[AttachmentTextBlock, ...]
    total_text_chars: int

    def as_dict(self) -> dict:
        return {
            "attachment_id": self.attachment_id,
            "source_url": self.source_url,
            "filename": self.filename,
            "extension": self.extension,
            "snapshot_sha256": self.snapshot_sha256,
            "parser_version": self.parser_version,
            "blocks": [block.as_dict() for block in self.blocks],
            "total_text_chars": self.total_text_chars,
        }


def _verify_snapshot(snapshot: AttachmentSnapshot) -> None:
    digest = hashlib.sha256(snapshot.body).hexdigest()
    if digest != snapshot.sha256:
        raise AttachmentParseError("SNAPSHOT_HASH_MISMATCH", "attachment bytes no longer match snapshot SHA-256")
    if snapshot.extension not in SUPPORTED_EXTENSIONS:
        raise AttachmentParseError(
            "PARSER_NOT_IMPLEMENTED",
            f"no deterministic local parser is implemented for {snapshot.extension}",
        )
    if not snapshot.body:
        raise AttachmentParseError("EMPTY_ATTACHMENT", "attachment body is empty")


def _open_bounded_zip(body: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(body), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise AttachmentParseError("INVALID_OOXML_ZIP", "OOXML package is not a valid ZIP archive") from exc

    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        archive.close()
        raise AttachmentParseError("OOXML_TOO_MANY_MEMBERS", f"OOXML package exceeds {MAX_ARCHIVE_MEMBERS} members")

    total = 0
    for info in infos:
        if info.flag_bits & 0x1:
            archive.close()
            raise AttachmentParseError("ENCRYPTED_OOXML", "encrypted OOXML members are not supported")
        normalized = posixpath.normpath(info.filename.replace("\\", "/"))
        if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
            archive.close()
            raise AttachmentParseError("UNSAFE_OOXML_MEMBER", f"unsafe OOXML member path: {info.filename}")
        total += int(info.file_size)
        if total > MAX_UNCOMPRESSED_BYTES:
            archive.close()
            raise AttachmentParseError(
                "OOXML_UNCOMPRESSED_TOO_LARGE",
                f"OOXML package exceeds {MAX_UNCOMPRESSED_BYTES} uncompressed bytes",
            )
    return archive


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        raw = archive.read(name)
    except KeyError as exc:
        raise AttachmentParseError("OOXML_REQUIRED_PART_MISSING", f"missing OOXML part: {name}") from exc
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise AttachmentParseError("OOXML_XML_INVALID", f"invalid XML in OOXML part: {name}") from exc


def _append_block(blocks: list[AttachmentTextBlock], block: AttachmentTextBlock, total_chars: int) -> int:
    total_chars += len(block.text)
    if total_chars > MAX_TEXT_CHARS:
        raise AttachmentParseError("PARSED_TEXT_TOO_LARGE", f"parsed text exceeds {MAX_TEXT_CHARS} characters")
    blocks.append(block)
    return total_chars


def _parse_docx(snapshot: AttachmentSnapshot, archive: zipfile.ZipFile) -> ParsedAttachmentText:
    root = _xml(archive, "word/document.xml")
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    blocks: list[AttachmentTextBlock] = []
    total_chars = 0
    paragraph_number = 0

    for paragraph in root.findall(".//w:p", ns):
        runs = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        text = "".join(runs).strip()
        if not text:
            continue
        paragraph_number += 1
        total_chars = _append_block(
            blocks,
            AttachmentTextBlock(
                kind="DOCX_PARAGRAPH",
                locator={"paragraph": paragraph_number},
                text=text,
            ),
            total_chars,
        )

    return ParsedAttachmentText(
        attachment_id=snapshot.attachment_id,
        source_url=snapshot.source_url,
        filename=snapshot.filename,
        extension=snapshot.extension,
        snapshot_sha256=snapshot.sha256,
        parser_version=PARSER_VERSION,
        blocks=tuple(blocks),
        total_text_chars=total_chars,
    )


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _xml(archive, "xl/sharedStrings.xml")
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("x:si", ns):
        parts = [node.text or "" for node in item.findall(".//x:t", ns)]
        values.append("".join(parts))
    return values


def _xlsx_sheet_targets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = _xml(archive, "xl/workbook.xml")
    rels = _xml(archive, "xl/_rels/workbook.xml.rels")
    ns = {
        "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    relationships = {
        node.attrib.get("Id"): node.attrib.get("Target")
        for node in rels.findall(f"{{{rel_ns}}}Relationship")
        if node.attrib.get("Id") and node.attrib.get("Target")
    }

    result: list[tuple[str, str]] = []
    sheets = workbook.find("x:sheets", ns)
    if sheets is None:
        return result
    for sheet in list(sheets):
        name = sheet.attrib.get("name") or "Sheet"
        rel_id = sheet.attrib.get(f"{{{ns['r']}}}id")
        target = relationships.get(rel_id)
        if not target:
            continue
        normalized = posixpath.normpath(posixpath.join("xl", target))
        if not normalized.startswith("xl/"):
            raise AttachmentParseError("UNSAFE_XLSX_RELATIONSHIP", f"worksheet target escapes xl/: {target}")
        result.append((name, normalized))
    return result


def _xlsx_cell_text(cell: ET.Element, shared: list[str], ns: dict[str, str]) -> str:
    # Formula cached values can be stale. Pilot v0.1 does not evaluate formulas and
    # does not promote their cached values as deterministic procurement text.
    if cell.find("x:f", ns) is not None:
        return ""

    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        parts = [node.text or "" for node in cell.findall(".//x:is/x:t", ns)]
        return "".join(parts)

    value_node = cell.find("x:v", ns)
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text
    if cell_type == "s":
        try:
            index = int(value)
            return shared[index]
        except (ValueError, IndexError):
            raise AttachmentParseError("XLSX_SHARED_STRING_INVALID", f"invalid shared string index: {value}")
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def _parse_xlsx(snapshot: AttachmentSnapshot, archive: zipfile.ZipFile) -> ParsedAttachmentText:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared = _xlsx_shared_strings(archive)
    blocks: list[AttachmentTextBlock] = []
    total_chars = 0
    cell_count = 0

    for sheet_name, target in _xlsx_sheet_targets(archive):
        root = _xml(archive, target)
        for cell in root.findall(".//x:c", ns):
            cell_count += 1
            if cell_count > MAX_XLSX_CELLS:
                raise AttachmentParseError("XLSX_TOO_MANY_CELLS", f"XLSX exceeds {MAX_XLSX_CELLS} cells")
            reference = cell.attrib.get("r") or f"CELL_{cell_count}"
            text = _xlsx_cell_text(cell, shared, ns).strip()
            if not text:
                continue
            total_chars = _append_block(
                blocks,
                AttachmentTextBlock(
                    kind="XLSX_RANGE",
                    locator={"sheet": sheet_name, "range": reference},
                    text=text,
                ),
                total_chars,
            )

    return ParsedAttachmentText(
        attachment_id=snapshot.attachment_id,
        source_url=snapshot.source_url,
        filename=snapshot.filename,
        extension=snapshot.extension,
        snapshot_sha256=snapshot.sha256,
        parser_version=PARSER_VERSION,
        blocks=tuple(blocks),
        total_text_chars=total_chars,
    )


def parse_attachment(snapshot: AttachmentSnapshot) -> ParsedAttachmentText:
    _verify_snapshot(snapshot)
    archive = _open_bounded_zip(snapshot.body)
    try:
        if snapshot.extension == ".docx":
            return _parse_docx(snapshot, archive)
        if snapshot.extension == ".xlsx":
            return _parse_xlsx(snapshot, archive)
        raise AttachmentParseError("PARSER_NOT_IMPLEMENTED", snapshot.extension)
    finally:
        archive.close()
