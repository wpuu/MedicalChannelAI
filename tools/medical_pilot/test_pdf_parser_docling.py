from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.attachment_parser import AttachmentParseError
from tools.medical_pilot.attachments import AttachmentSnapshot
from tools.medical_pilot.pdf_parser_docling import (
    _verify_pdf_snapshot,
    extract_grounded_docling_blocks,
)


class FakeBBox:
    def __init__(self, l: float, t: float, r: float, b: float) -> None:
        self.l = l
        self.t = t
        self.r = r
        self.b = b
        self.coord_origin = "TOPLEFT"


class FakeProv:
    def __init__(self, page_no: int, bbox: FakeBBox, charspan=(0, 10)) -> None:
        self.page_no = page_no
        self.bbox = bbox
        self.charspan = charspan


class FakeTextItem:
    def __init__(self, text: str, prov, self_ref="#/texts/1") -> None:
        self.text = text
        self.prov = prov
        self.self_ref = self_ref


class FakeTableItem:
    def __init__(self, rendered: str, prov, self_ref="#/tables/1") -> None:
        self.rendered = rendered
        self.prov = prov
        self.self_ref = self_ref

    def export_to_markdown(self, doc=None) -> str:
        return self.rendered


class FakeDocument:
    def __init__(self, items) -> None:
        self.items = list(items)

    def iterate_items(self, with_groups=False):
        return [(item, 0) for item in self.items]


def pdf_snapshot(body: bytes) -> AttachmentSnapshot:
    return AttachmentSnapshot(
        attachment_id="att_pdf_fixture",
        source_url="https://example.invalid/medical.pdf",
        filename="medical.pdf",
        extension=".pdf",
        fetched_at="2026-08-28T09:00:00Z",
        status_code=200,
        content_type="application/pdf",
        size_bytes=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        body=body,
        parser_eligible=False,
    )


class DoclingPdfParserContractTests(unittest.TestCase):
    def test_pdf_signature_and_snapshot_hash_are_required(self) -> None:
        valid = pdf_snapshot(b"%PDF-1.7\nfixture")
        _verify_pdf_snapshot(valid)

        invalid_signature = pdf_snapshot(b"not a pdf")
        with self.assertRaises(AttachmentParseError) as context:
            _verify_pdf_snapshot(invalid_signature)
        self.assertEqual(context.exception.code, "INVALID_PDF_SIGNATURE")

        tampered = AttachmentSnapshot(
            attachment_id=valid.attachment_id,
            source_url=valid.source_url,
            filename=valid.filename,
            extension=valid.extension,
            fetched_at=valid.fetched_at,
            status_code=valid.status_code,
            content_type=valid.content_type,
            size_bytes=valid.size_bytes,
            sha256="0" * 64,
            body=valid.body,
            parser_eligible=False,
        )
        with self.assertRaises(AttachmentParseError) as context:
            _verify_pdf_snapshot(tampered)
        self.assertEqual(context.exception.code, "SNAPSHOT_HASH_MISMATCH")

    def test_only_grounded_text_is_emitted(self) -> None:
        grounded = FakeTextItem(
            "预算金额250万元",
            [FakeProv(3, FakeBBox(10, 20, 200, 40), (100, 110))],
        )
        ungrounded = FakeTextItem("模型可能生成的无出处文本", [])
        blocks = extract_grounded_docling_blocks(FakeDocument([grounded, ungrounded]))

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "PDF_TEXT")
        self.assertEqual(blocks[0].text, "预算金额250万元")
        provenance = blocks[0].locator["provenance"]
        self.assertEqual(provenance[0]["page_no"], 3)
        self.assertEqual(provenance[0]["charspan"], [100, 110])
        self.assertEqual(provenance[0]["bbox"]["l"], 10.0)

    def test_table_markdown_keeps_page_bbox_provenance(self) -> None:
        table = FakeTableItem(
            "| 名称 | 品牌 |\n|---|---|\n| DR | 联影 |",
            [FakeProv(7, FakeBBox(30, 100, 500, 300), (0, 30))],
        )
        blocks = extract_grounded_docling_blocks(FakeDocument([table]))

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "PDF_TABLE")
        self.assertIn("联影", blocks[0].text)
        self.assertEqual(blocks[0].locator["provenance"][0]["page_no"], 7)

    def test_items_with_page_but_missing_bbox_are_not_evidence_blocks(self) -> None:
        missing_bbox = FakeTextItem("不能成为 VERIFIED Evidence", [FakeProv(1, None)])
        blocks = extract_grounded_docling_blocks(FakeDocument([missing_bbox]))
        self.assertEqual(blocks, ())

    def test_document_without_iterate_items_fails_closed(self) -> None:
        with self.assertRaises(AttachmentParseError) as context:
            extract_grounded_docling_blocks(object())
        self.assertEqual(context.exception.code, "DOCLING_DOCUMENT_API_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
