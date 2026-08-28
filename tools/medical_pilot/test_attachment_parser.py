from __future__ import annotations

import hashlib
import io
import unittest
import zipfile

from tools.medical_pilot.attachment_parser import AttachmentParseError, parse_attachment
from tools.medical_pilot.attachments import AttachmentSnapshot


def zipped(parts: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value.encode("utf-8") if isinstance(value, str) else value)
    return buffer.getvalue()


def snapshot(extension: str, body: bytes, *, digest: str | None = None) -> AttachmentSnapshot:
    actual = hashlib.sha256(body).hexdigest()
    return AttachmentSnapshot(
        attachment_id="att_00000000-0000-0000-0000-000000000001",
        source_url=f"https://www.ccgp.gov.cn/files/fixture{extension}",
        filename=f"fixture{extension}",
        extension=extension,
        fetched_at="2026-08-28T06:00:00Z",
        status_code=200,
        content_type="application/octet-stream",
        size_bytes=len(body),
        sha256=digest or actual,
        body=body,
        parser_eligible=extension in {".docx", ".xlsx"},
    )


def docx_fixture() -> bytes:
    return zipped(
        {
            "word/document.xml": """<?xml version='1.0' encoding='UTF-8'?>
<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
  <w:body>
    <w:p><w:r><w:t>项目名称：天津市胸科医院检验设备采购项目</w:t></w:r></w:p>
    <w:p><w:r><w:t>预算金额：</w:t></w:r><w:r><w:t>573万元</w:t></w:r></w:p>
  </w:body>
</w:document>""",
        }
    )


def xlsx_fixture() -> bytes:
    return zipped(
        {
            "xl/workbook.xml": """<?xml version='1.0' encoding='UTF-8'?>
<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
 xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>
  <sheets><sheet name='设备清单' sheetId='1' r:id='rId1'/></sheets>
</workbook>""",
            "xl/_rels/workbook.xml.rels": """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
  <Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet' Target='worksheets/sheet1.xml'/>
</Relationships>""",
            "xl/sharedStrings.xml": """<?xml version='1.0' encoding='UTF-8'?>
<sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>
  <si><t>设备名称</t></si>
  <si><t>全自动生化分析仪</t></si>
</sst>""",
            "xl/worksheets/sheet1.xml": """<?xml version='1.0' encoding='UTF-8'?>
<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>
  <sheetData>
    <row r='1'><c r='A1' t='s'><v>0</v></c><c r='B1' t='inlineStr'><is><t>数量</t></is></c></row>
    <row r='2'><c r='A2' t='s'><v>1</v></c><c r='B2'><v>2</v></c><c r='C2'><f>B2*100</f><v>200</v></c></row>
  </sheetData>
</worksheet>""",
        }
    )


class AttachmentParserTests(unittest.TestCase):
    def test_docx_preserves_paragraph_evidence_locators(self) -> None:
        parsed = parse_attachment(snapshot(".docx", docx_fixture()))
        self.assertEqual(parsed.parser_version, "ooxml-stdlib-v0.1")
        self.assertEqual([block.kind for block in parsed.blocks], ["DOCX_PARAGRAPH", "DOCX_PARAGRAPH"])
        self.assertEqual(parsed.blocks[0].locator, {"paragraph": 1})
        self.assertIn("天津市胸科医院", parsed.blocks[0].text)
        self.assertEqual(parsed.blocks[1].text, "预算金额：573万元")

    def test_xlsx_preserves_sheet_and_cell_locator_and_skips_formula_cache(self) -> None:
        parsed = parse_attachment(snapshot(".xlsx", xlsx_fixture()))
        by_range = {block.locator["range"]: block for block in parsed.blocks}
        self.assertEqual(by_range["A1"].text, "设备名称")
        self.assertEqual(by_range["A2"].text, "全自动生化分析仪")
        self.assertEqual(by_range["B2"].text, "2")
        self.assertEqual(by_range["A2"].locator["sheet"], "设备清单")
        self.assertNotIn("C2", by_range)

    def test_snapshot_hash_mismatch_fails_before_parsing(self) -> None:
        body = docx_fixture()
        bad_digest = "0" * 64
        with self.assertRaises(AttachmentParseError) as context:
            parse_attachment(snapshot(".docx", body, digest=bad_digest))
        self.assertEqual(context.exception.code, "SNAPSHOT_HASH_MISMATCH")

    def test_pdf_and_legacy_office_fail_closed_until_parser_exists(self) -> None:
        for extension, body in ((".pdf", b"%PDF-1.7"), (".doc", b"legacy-doc"), (".xls", b"legacy-xls")):
            with self.subTest(extension=extension):
                with self.assertRaises(AttachmentParseError) as context:
                    parse_attachment(snapshot(extension, body))
                self.assertEqual(context.exception.code, "PARSER_NOT_IMPLEMENTED")

    def test_unsafe_ooxml_member_path_is_rejected_even_without_extraction(self) -> None:
        body = zipped(
            {
                "word/document.xml": """<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body/></w:document>""",
                "../evil.xml": "nope",
            }
        )
        with self.assertRaises(AttachmentParseError) as context:
            parse_attachment(snapshot(".docx", body))
        self.assertEqual(context.exception.code, "UNSAFE_OOXML_MEMBER")


if __name__ == "__main__":
    unittest.main()
