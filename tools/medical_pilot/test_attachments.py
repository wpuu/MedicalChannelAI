from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from tools.medical_pilot.attachments import (
    AttachmentCandidate,
    BoundedAttachmentFetcher,
    discover_attachments,
)
from tools.medical_pilot.collector_core import FetchError


class FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class FakeResponse:
    def __init__(self, url: str, body: bytes, content_type: str) -> None:
        self._url = url
        self._body = body
        self.headers = FakeHeaders(content_type)
        self.status = 200

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]


class AttachmentDiscoveryTests(unittest.TestCase):
    def test_discovers_downloadable_files_and_exposes_real_parser_status(self) -> None:
        html = """
        <a href='/files/project.pdf'>项目需求.pdf</a>
        <a href='/files/spec.xlsx'>设备清单.xlsx</a>
        <a href='/files/archive.zip'>其他附件.zip</a>
        <a href='/download?id=123'>采购文件.docx</a>
        <a href='/files/legacy.xls'>历史清单.xls</a>
        <a href='/files/readme.txt'>说明.txt</a>
        """
        found = discover_attachments(html, "https://www.ccgp.gov.cn/notice.htm")
        by_name = {item.filename: item for item in found}
        self.assertIn("project.pdf", by_name)
        self.assertIn("spec.xlsx", by_name)
        self.assertIn("archive.zip", by_name)
        self.assertIn("采购文件.docx", by_name)
        self.assertIn("legacy.xls", by_name)
        self.assertNotIn("readme.txt", by_name)
        self.assertEqual(by_name["archive.zip"].handling_policy, "DISCOVER_ONLY_ARCHIVE")
        self.assertEqual(by_name["project.pdf"].handling_policy, "DOWNLOAD_ONLY_PARSER_PENDING")
        self.assertEqual(by_name["legacy.xls"].handling_policy, "DOWNLOAD_ONLY_PARSER_PENDING")
        self.assertEqual(by_name["spec.xlsx"].handling_policy, "DOWNLOAD_AND_PARSE_APPROVED")
        self.assertEqual(by_name["采购文件.docx"].handling_policy, "DOWNLOAD_AND_PARSE_APPROVED")

    def test_archive_cannot_be_downloaded_by_pilot_fetcher(self) -> None:
        candidate = AttachmentCandidate(
            source_url="https://www.ccgp.gov.cn/files/a.zip",
            filename="a.zip",
            extension=".zip",
            title="a.zip",
            handling_policy="DISCOVER_ONLY_ARCHIVE",
        )
        with self.assertRaises(FetchError) as context:
            BoundedAttachmentFetcher({"www.ccgp.gov.cn"}).fetch(candidate)
        self.assertEqual(context.exception.code, "ARCHIVE_DOWNLOAD_DISABLED")

    def test_unregistered_attachment_host_is_rejected_before_network(self) -> None:
        candidate = AttachmentCandidate(
            source_url="https://evil.example/spec.pdf",
            filename="spec.pdf",
            extension=".pdf",
            title="spec.pdf",
            handling_policy="DOWNLOAD_ONLY_PARSER_PENDING",
        )
        with self.assertRaises(FetchError) as context:
            BoundedAttachmentFetcher({"www.ccgp.gov.cn"}).fetch(candidate)
        self.assertEqual(context.exception.code, "ATTACHMENT_HOST_NOT_ALLOWED")

    def test_discovered_but_unvalidated_route_is_rejected_before_network(self) -> None:
        candidate = AttachmentCandidate(
            source_url="https://www.ccgp.gov.cn/files/spec.pdf",
            filename="spec.pdf",
            extension=".pdf",
            title="spec.pdf",
            handling_policy="DISCOVER_ONLY_PENDING_BYTES_VALIDATION",
            download_authorized=False,
        )
        with self.assertRaises(FetchError) as context:
            BoundedAttachmentFetcher({"www.ccgp.gov.cn"}).fetch(candidate)
        self.assertEqual(context.exception.code, "ATTACHMENT_DOWNLOAD_NOT_AUTHORIZED")

    @patch("urllib.request.urlopen")
    def test_downloaded_pdf_has_hash_but_is_not_falsely_marked_parser_eligible(self, mocked_urlopen) -> None:
        body = b"%PDF-1.7\nmedical pilot fixture"
        url = "https://www.ccgp.gov.cn/files/spec.pdf"
        mocked_urlopen.return_value = FakeResponse(url, body, "application/pdf")
        candidate = AttachmentCandidate(
            source_url=url,
            filename="spec.pdf",
            extension=".pdf",
            title="spec.pdf",
            handling_policy="DOWNLOAD_ONLY_PARSER_PENDING",
        )
        result = BoundedAttachmentFetcher({"www.ccgp.gov.cn"}).fetch(candidate)
        self.assertEqual(result.sha256, hashlib.sha256(body).hexdigest())
        self.assertTrue(result.attachment_id.startswith("att_"))
        self.assertEqual(result.size_bytes, len(body))
        self.assertFalse(result.parser_eligible)

    @patch("urllib.request.urlopen")
    def test_downloaded_xlsx_is_marked_parser_eligible(self, mocked_urlopen) -> None:
        body = b"PK\x03\x04minimal-fixture"
        url = "https://www.ccgp.gov.cn/files/spec.xlsx"
        mocked_urlopen.return_value = FakeResponse(
            url,
            body,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        candidate = AttachmentCandidate(
            source_url=url,
            filename="spec.xlsx",
            extension=".xlsx",
            title="spec.xlsx",
            handling_policy="DOWNLOAD_AND_PARSE_APPROVED",
        )
        result = BoundedAttachmentFetcher({"www.ccgp.gov.cn"}).fetch(candidate)
        self.assertTrue(result.parser_eligible)

    @patch("urllib.request.urlopen")
    def test_mime_mismatch_fails_closed(self, mocked_urlopen) -> None:
        url = "https://www.ccgp.gov.cn/files/spec.pdf"
        mocked_urlopen.return_value = FakeResponse(url, b"<html>not pdf</html>", "text/html")
        candidate = AttachmentCandidate(
            source_url=url,
            filename="spec.pdf",
            extension=".pdf",
            title="spec.pdf",
            handling_policy="DOWNLOAD_ONLY_PARSER_PENDING",
        )
        with self.assertRaises(FetchError) as context:
            BoundedAttachmentFetcher({"www.ccgp.gov.cn"}).fetch(candidate)
        self.assertEqual(context.exception.code, "ATTACHMENT_MIME_MISMATCH")

    @patch("urllib.request.urlopen")
    def test_allowed_octet_stream_with_wrong_ooxml_magic_fails_closed(self, mocked_urlopen) -> None:
        url = "https://www.ccgp.gov.cn/files/spec.docx"
        mocked_urlopen.return_value = FakeResponse(url, b"<html>fake docx</html>", "application/octet-stream")
        candidate = AttachmentCandidate(
            source_url=url,
            filename="spec.docx",
            extension=".docx",
            title="spec.docx",
            handling_policy="DOWNLOAD_AND_PARSE_APPROVED",
        )
        with self.assertRaises(FetchError) as context:
            BoundedAttachmentFetcher({"www.ccgp.gov.cn"}).fetch(candidate)
        self.assertEqual(context.exception.code, "ATTACHMENT_MAGIC_MISMATCH")


if __name__ == "__main__":
    unittest.main()
