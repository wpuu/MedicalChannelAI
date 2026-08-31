from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.medical_pilot.attachment_live_probe import (
    AttachmentLiveProbeError,
    probe_attachment,
    validate_probe_filename,
    validate_tianjin_finance_attachment_url,
)


VALID_URL = "https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=1OQ5vSM9GqM%2A&method=downEnId"


class AttachmentLiveProbePolicyTest(unittest.TestCase):
    def test_accepts_exact_official_downenid_route(self) -> None:
        validate_tianjin_finance_attachment_url(VALID_URL)

    def test_rejects_non_https(self) -> None:
        with self.assertRaisesRegex(AttachmentLiveProbeError, "HTTPS"):
            validate_tianjin_finance_attachment_url(VALID_URL.replace("https://", "http://"))

    def test_rejects_unapproved_host(self) -> None:
        with self.assertRaisesRegex(AttachmentLiveProbeError, "approved Tianjin government host"):
            validate_tianjin_finance_attachment_url(
                "https://example.com/portal/documentView.do?id=x&method=downEnId"
            )

    def test_rejects_wrong_method_or_extra_query(self) -> None:
        with self.assertRaises(AttachmentLiveProbeError):
            validate_tianjin_finance_attachment_url(
                "https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=x&method=view"
            )
        with self.assertRaises(AttachmentLiveProbeError):
            validate_tianjin_finance_attachment_url(VALID_URL + "&tenant=should-not-exist")

    def test_filename_is_basename_and_ooxml_only(self) -> None:
        self.assertEqual(validate_probe_filename("项目需求书.docx"), ".docx")
        self.assertEqual(validate_probe_filename("明细.xlsx"), ".xlsx")
        with self.assertRaises(AttachmentLiveProbeError):
            validate_probe_filename("../项目需求书.docx")
        with self.assertRaises(AttachmentLiveProbeError):
            validate_probe_filename("项目需求书.pdf")

    def test_probe_returns_metadata_only(self) -> None:
        snapshot = SimpleNamespace(
            source_url=VALID_URL,
            filename="XCSD-2026-C-181项目需求书.docx",
            extension=".docx",
            status_code=200,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=12345,
            sha256="a" * 64,
        )
        parsed = SimpleNamespace(
            parser_version="ooxml-stdlib-v0.1",
            blocks=(SimpleNamespace(text="基因测序仪"),),
            total_text_chars=5,
        )
        classification = SimpleNamespace(
            validation_status="UNVERIFIED",
            labels=(),
        )
        fetcher = Mock()
        fetcher.fetch.return_value = snapshot

        with (
            patch(
                "tools.medical_pilot.attachment_live_probe.BoundedAttachmentFetcher",
                return_value=fetcher,
            ),
            patch(
                "tools.medical_pilot.attachment_live_probe.parse_attachment",
                return_value=parsed,
            ),
            patch(
                "tools.medical_pilot.attachment_live_probe.classify_product_facts",
                return_value=classification,
            ),
        ):
            result = probe_attachment(
                url=VALID_URL,
                filename="XCSD-2026-C-181项目需求书.docx",
            )

        self.assertEqual(result["sha256"], "a" * 64)
        self.assertEqual(result["block_count"], 1)
        self.assertEqual(result["taxonomy_labels"], [])
        self.assertNotIn("body", result)
        self.assertNotIn("text", result)
        self.assertNotIn("parsed_blocks", result)
        self.assertNotIn("source_url", result)


if __name__ == "__main__":
    unittest.main()
