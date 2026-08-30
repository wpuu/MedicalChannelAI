from __future__ import annotations

import unittest

from tools.medical_pilot.followup_feedback import build_profile_learning_suggestions


BASE = {
    "schema_version": "0.1",
    "followup_id": "mfollow_11111111-1111-1111-1111-111111111111",
    "tenant_id": "tenant-demo",
    "opportunity_id": "opp_22222222-2222-2222-2222-222222222222",
    "status": "NOT_FIT",
    "owner": "销售A",
    "recorded_at": "2026-08-29T08:00:00+08:00",
    "customer_confirmed": True,
}


class FollowupFeedbackTests(unittest.TestCase):
    def test_no_product_capability_suggests_profile_review_but_never_auto_applies(self) -> None:
        followup = dict(BASE, not_fit_reason="NO_PRODUCT_CAPABILITY")
        result = build_profile_learning_suggestions(followup)
        self.assertEqual(result["learning_status"], "PROFILE_REVIEW_SUGGESTED")
        self.assertEqual(result["suggestions"][0]["code"], "REVIEW_PRODUCT_CAPABILITY_SCOPE")
        self.assertFalse(result["suggestions"][0]["auto_apply_allowed"])

    def test_unconfirmed_feedback_cannot_train_profile(self) -> None:
        followup = dict(BASE, not_fit_reason="AMOUNT_TOO_SMALL", customer_confirmed=False)
        result = build_profile_learning_suggestions(followup)
        self.assertEqual(result["learning_status"], "REQUIRES_CUSTOMER_CONFIRMATION")
        self.assertEqual(result["suggestions"], [])

    def test_competitor_locked_is_project_specific_not_global_rule(self) -> None:
        followup = dict(BASE, not_fit_reason="COMPETITOR_LOCKED_CUSTOMER_JUDGMENT")
        result = build_profile_learning_suggestions(followup)
        self.assertEqual(result["learning_status"], "PROJECT_SPECIFIC_ONLY")
        self.assertIn("PROJECT_SPECIFIC_FEEDBACK_DO_NOT_GENERALIZE_TO_PROFILE", result["warnings"])

    def test_non_not_fit_status_does_not_modify_profile(self) -> None:
        followup = dict(BASE, status="CONTACTED", not_fit_reason=None)
        result = build_profile_learning_suggestions(followup)
        self.assertEqual(result["learning_status"], "NO_PROFILE_LEARNING_TRIGGER")
        self.assertEqual(result["suggestions"], [])


if __name__ == "__main__":
    unittest.main()
