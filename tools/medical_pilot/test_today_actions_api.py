from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.medical_pilot.agnes_task_result import MemoryAgnesTaskResultStore
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions_api import (
    build_today_actions_api_response,
    get_today_opportunity_api_response,
)


NOW = datetime(2026, 8, 30, 8, 10, tzinfo=ZoneInfo("Asia/Shanghai"))


def evidence_for(item: dict) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": "fact_api_demo",
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": item["project_name"],
        "source_url": "https://www.ccgp.gov.cn/example/api",
    }


class Repository:
    def __init__(self) -> None:
        self.profile = complete_profile()
        self.item = opportunity()
        self.list_calls: list[tuple[str, int]] = []
        self.evidence_calls: list[list[str]] = []

    def load_profile(self, tenant_id: str, profile_id: str):
        if tenant_id != self.profile["tenant_id"] or profile_id != self.profile["profile_id"]:
            return None
        return self.profile

    def list_opportunities(self, tenant_id: str, profile: dict, *, limit: int):
        self.list_calls.append((tenant_id, limit))
        return [self.item]

    def load_evidence(self, tenant_id: str, opportunity_ids: list[str]):
        self.evidence_calls.append(list(opportunity_ids))
        return {self.item["opportunity_id"]: [evidence_for(self.item)]}


class TodayActionsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repository()
        self.results = MemoryAgnesTaskResultStore()
        self.tenant_id = self.repo.profile["tenant_id"]
        self.profile_id = self.repo.profile["profile_id"]

    def test_today_returns_public_view_only_and_enqueues_internal_dispatch_server_side(self) -> None:
        dispatched: list[dict] = []
        response = build_today_actions_api_response(
            tenant_id=self.tenant_id,
            profile_id=self.profile_id,
            repository=self.repo,
            result_store=self.results,
            now=NOW,
            dispatch_sink=dispatched.append,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("model_requests", response.body)
        self.assertNotIn("agnes_dispatch_plan", response.body)
        self.assertNotIn("task_payloads", response.body)
        self.assertEqual(response.body["card_count"], 1)
        self.assertEqual(response.body["model_request_count"], 1)
        self.assertEqual(len(dispatched), 1)
        self.assertIn("task_payloads", dispatched[0])

    def test_repository_candidate_query_uses_query_budget_limit(self) -> None:
        build_today_actions_api_response(
            tenant_id=self.tenant_id,
            profile_id=self.profile_id,
            repository=self.repo,
            result_store=self.results,
            now=NOW,
        )
        self.assertEqual(self.repo.list_calls, [(self.tenant_id, 500)])

    def test_cross_tenant_or_unknown_profile_returns_same_404_without_candidate_query(self) -> None:
        response = build_today_actions_api_response(
            tenant_id="other-tenant",
            profile_id=self.profile_id,
            repository=self.repo,
            result_store=self.results,
            now=NOW,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.body, {"error": "PROFILE_NOT_FOUND"})
        self.assertEqual(self.repo.list_calls, [])

    def test_opportunity_detail_is_selected_only_from_current_tenant_today_cards(self) -> None:
        found = get_today_opportunity_api_response(
            tenant_id=self.tenant_id,
            profile_id=self.profile_id,
            opportunity_id=self.repo.item["opportunity_id"],
            repository=self.repo,
            result_store=self.results,
            now=NOW,
        )
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.body["opportunity_id"], self.repo.item["opportunity_id"])

        missing = get_today_opportunity_api_response(
            tenant_id=self.tenant_id,
            profile_id=self.profile_id,
            opportunity_id="opp_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            repository=self.repo,
            result_store=self.results,
            now=NOW,
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.body, {"error": "OPPORTUNITY_NOT_FOUND"})


if __name__ == "__main__":
    unittest.main()
