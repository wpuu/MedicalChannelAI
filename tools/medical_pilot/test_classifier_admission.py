from __future__ import annotations

import unittest

from tools.medical_pilot.classifier_admission import (
    classifier_can_drive_matching,
    load_classifier_admissions,
)


class ClassifierAdmissionTests(unittest.TestCase):
    def test_deterministic_classifier_is_admitted(self) -> None:
        admitted, reason = classifier_can_drive_matching(
            "deterministic-product-taxonomy-v0.1", "DETERMINISTIC"
        )
        self.assertTrue(admitted)
        self.assertEqual(reason, "VALIDATED")

    def test_human_classifier_is_admitted(self) -> None:
        admitted, reason = classifier_can_drive_matching(
            "human-confirmed-product-taxonomy-v0.1", "HUMAN_CONFIRMED"
        )
        self.assertTrue(admitted)
        self.assertEqual(reason, "VALIDATED")

    def test_agnes_classifier_stays_blocked_until_global_benchmark_admission(self) -> None:
        admissions = load_classifier_admissions()
        agnes = admissions["agnes-2.5-flash-product-taxonomy-v0.1"]
        self.assertEqual(agnes.admission_status, "BENCHMARK_PENDING")
        self.assertFalse(agnes.can_drive_matching)
        admitted, reason = classifier_can_drive_matching(
            agnes.classifier_id, "CONTROLLED_MODEL_CLASSIFICATION"
        )
        self.assertFalse(admitted)
        self.assertEqual(reason, "CLASSIFIER_NOT_ADMITTED")

    def test_kind_mismatch_fails_closed(self) -> None:
        admitted, reason = classifier_can_drive_matching(
            "deterministic-product-taxonomy-v0.1", "CONTROLLED_MODEL_CLASSIFICATION"
        )
        self.assertFalse(admitted)
        self.assertEqual(reason, "CLASSIFIER_KIND_MISMATCH")

    def test_unknown_classifier_fails_closed(self) -> None:
        admitted, reason = classifier_can_drive_matching(
            "not-registered", "DETERMINISTIC"
        )
        self.assertFalse(admitted)
        self.assertEqual(reason, "CLASSIFIER_NOT_REGISTERED")


if __name__ == "__main__":
    unittest.main()
