from __future__ import annotations

import unittest

from tools.medical_pilot.match_pipeline import evaluate_match_pipeline
from tools.medical_pilot.priority_score import PriorityScoreError, calculate_priority_score
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


class PriorityScoreTests(unittest.TestCase):
    def matched(self, *, confirmed: bool = True, relationship: str | None = None, stage: str = "TENDERING"):
        profile = complete_profile(confirmed=confirmed)
        item = opportunity()
        item["hospital_name"] = "天津测试医院"
        item["lifecycle_state"] = stage
        item["product_label_provenance"] = "DETERMINISTIC"
        item["product_label_validation_status"] = "VALIDATED"
        item["product_classifier_id"] = "deterministic-product-taxonomy-v0.1"
        if relationship is not None:
            profile["hospital_relationships"] = [
                {
                    "hospital_name": "天津测试医院",
                    "department": "检验科",
                    "relationship_strength": relationship,
                    "owner": "销售A",
                    "confirmed_by_customer": True,
                    "last_confirmed_at": "2026-08-28T20:00:00+08:00",
                }
            ]
        match = evaluate_match_pipeline(profile, item)
        return profile, item, match

    def test_strong_relationship_formal_tender_scores_85(self) -> None:
        profile, item, match = self.matched(relationship="STRONG")
        score = calculate_priority_score(profile, item, match)
        self.assertEqual(score.score, 85)
        self.assertEqual(score.score_type, "PERSONALIZED_PRIORITY")
        self.assertEqual({component.code for component in score.components}, {
            "PRODUCT_EXECUTION_CAPABILITY",
            "RELATIONSHIP",
            "INTERVENTION_STAGE",
            "PROJECT_AMOUNT",
        })
        self.assertEqual(score.as_dict()["interpretation"], "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY")

    def test_unknown_relationship_does_not_get_invented_points(self) -> None:
        profile, item, match = self.matched(relationship=None)
        score = calculate_priority_score(profile, item, match)
        relationship_component = next(component for component in score.components if component.code == "RELATIONSHIP")
        self.assertEqual(relationship_component.points, 0)
        self.assertIn("RELATIONSHIP_UNKNOWN", score.warnings)
        self.assertEqual(score.score, 60)

    def test_early_stage_gets_more_intervention_points_but_not_win_probability(self) -> None:
        profile, item, match = self.matched(relationship="STRONG", stage="MARKET_RESEARCH")
        score = calculate_priority_score(profile, item, match)
        self.assertEqual(score.score, 95)
        self.assertEqual(score.as_dict()["interpretation"], "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY")

    def test_unconfirmed_profile_uses_candidate_priority_label(self) -> None:
        profile, item, match = self.matched(confirmed=False, relationship="MEDIUM")
        score = calculate_priority_score(profile, item, match)
        self.assertEqual(score.score_type, "CANDIDATE_PRIORITY")

    def test_non_matched_opportunity_cannot_be_scored(self) -> None:
        profile, item, match = self.matched()
        item["verification_status"] = "UNVERIFIED"
        blocked = evaluate_match_pipeline(profile, item)
        with self.assertRaises(PriorityScoreError) as context:
            calculate_priority_score(profile, item, blocked)
        self.assertEqual(context.exception.code, "MATCH_REQUIRED")


if __name__ == "__main__":
    unittest.main()
