from __future__ import annotations

import json
import unittest

from tools.medical_pilot.agnes_client import AgnesChatClient, AgnesClientError, validate_base_url


MODEL_INPUT = {
    "schema_version": "0.1",
    "opportunity_id": "opp_22222222-2222-2222-2222-222222222222",
    "match_status": "MATCHED_PERSONALIZED",
    "recommendation_mode": "PERSONALIZED_RECOMMENDATION",
    "lifecycle_state": "TENDERING",
    "allowed_action_types": ["PREPARE_BID", "MONITOR"],
    "allowed_reason_codes": ["FORMAL_TENDER"],
    "allowed_risk_codes": ["COVERAGE_PARTIAL"],
    "grounded_facts": [
        {
            "fact_id": "fact_demo",
            "field_name": "project_name",
            "field_value": "测试项目",
            "source_url": "https://www.ccgp.gov.cn/example",
        }
    ],
    "confirmed_profile_context": {"business_role": "LOCAL_DISTRIBUTOR"},
    "input_budget": {
        "source_verified_fact_count": 1,
        "included_fact_count": 1,
        "omitted_fact_count": 0,
        "included_fact_chars": 20,
        "max_facts": 24,
        "max_fact_chars": 12000,
    },
    "instruction": "locked",
}


class AgnesClientTests(unittest.TestCase):
    def test_only_official_exact_https_base_urls_are_allowed(self) -> None:
        allowed = [
            "https://apihub.agnes-ai.com/v1",
            "https://apihub.agnes-ai.cn/v1",
            "https://api.agnes-ai.cn/v1",
        ]
        for value in allowed:
            with self.subTest(value=value):
                self.assertEqual(validate_base_url(value), value)
        rejected = [
            "http://apihub.agnes-ai.com/v1",
            "https://evil.example/v1",
            "https://apihub.agnes-ai.com/v1/extra",
            "https://apihub.agnes-ai.com:8443/v1",
            "https://apihub.agnes-ai.com/v1?x=1",
        ]
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_base_url(value)

    def test_request_is_non_streaming_agnes_25_flash_and_key_is_header_only(self) -> None:
        client = AgnesChatClient(api_key="secret-test-key")
        request = client.build_request(MODEL_INPUT)
        self.assertEqual(request.full_url, "https://apihub.agnes-ai.com/v1/chat/completions")
        body = request.data.decode("utf-8")
        payload = json.loads(body)
        self.assertEqual(payload["model"], "agnes-2.5-flash")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["temperature"], 0)
        self.assertNotIn("secret-test-key", body)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-test-key")

    def test_exact_json_model_content_is_returned_as_object(self) -> None:
        calls = []

        def transport(request, timeout):
            calls.append((request.full_url, timeout))
            output = {
                "schema_version": "0.1",
                "opportunity_id": MODEL_INPUT["opportunity_id"],
                "action_type": "PREPARE_BID",
                "reason_codes": ["FORMAL_TENDER"],
                "risk_codes": ["COVERAGE_PARTIAL"],
                "supporting_fact_ids": ["fact_demo"],
                "supporting_profile_paths": [],
                "requires_human_confirmation": True,
            }
            envelope = {"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]}
            return 200, json.dumps(envelope, ensure_ascii=False).encode("utf-8")

        client = AgnesChatClient(api_key="secret", transport=transport)
        result = client(MODEL_INPUT)
        self.assertEqual(result["action_type"], "PREPARE_BID")
        self.assertEqual(len(calls), 1)

    def test_fenced_or_non_json_content_is_not_silently_massaged(self) -> None:
        def fenced_transport(request, timeout):
            envelope = {"choices": [{"message": {"content": "```json\n{}\n```"}}]}
            return 200, json.dumps(envelope).encode("utf-8")

        with self.assertRaises(AgnesClientError) as context:
            AgnesChatClient(api_key="secret", transport=fenced_transport)(MODEL_INPUT)
        self.assertEqual(context.exception.error_class, "MODEL_JSON_INVALID")
        self.assertFalse(context.exception.retryable)

    def test_http_429_and_5xx_keep_retry_classification_without_route_rotation(self) -> None:
        for status, expected in [(429, "HTTP_429"), (503, "HTTP_5XX")]:
            with self.subTest(status=status):
                calls = []

                def transport(request, timeout, status=status):
                    calls.append(request.full_url)
                    return status, b"{}"

                client = AgnesChatClient(
                    api_key="secret",
                    base_url="https://api.agnes-ai.cn/v1",
                    transport=transport,
                )
                with self.assertRaises(AgnesClientError) as context:
                    client(MODEL_INPUT)
                self.assertEqual(context.exception.error_class, expected)
                self.assertTrue(context.exception.retryable)
                self.assertEqual(calls, ["https://api.agnes-ai.cn/v1/chat/completions"])

    def test_auth_or_request_4xx_is_non_retryable_and_does_not_change_endpoint(self) -> None:
        calls = []

        def transport(request, timeout):
            calls.append(request.full_url)
            return 401, b"{}"

        client = AgnesChatClient(
            api_key="secret",
            base_url="https://apihub.agnes-ai.com/v1",
            transport=transport,
        )
        with self.assertRaises(AgnesClientError) as context:
            client(MODEL_INPUT)
        self.assertEqual(context.exception.error_class, "HTTP_4XX")
        self.assertFalse(context.exception.retryable)
        self.assertEqual(calls, ["https://apihub.agnes-ai.com/v1/chat/completions"])


if __name__ == "__main__":
    unittest.main()
