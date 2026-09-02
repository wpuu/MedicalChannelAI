import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class TodayFeedbackAttentionTests(unittest.TestCase):
    def test_feedback_changes_today_attention_without_mutating_full_pool(self):
        source = (WEB_ROOT / "api" / "private.js").read_text(encoding="utf-8")
        start = source.index("async function todayFeedbackMap")
        end = source.index("async function opportunityRoute")
        today_source = source[start:end]

        self.assertIn("FROM private_recommendation_feedback", today_source)
        self.assertIn("feedback === 'NEW_NOT_VALUABLE'", today_source)
        self.assertIn("feedback === 'ALREADY_KNOWN'", today_source)
        self.assertIn("if (hasActiveFollowup(followup)) return 0", today_source)
        self.assertIn(".filter((item) => item.tier < 2)", today_source)
        self.assertIn("opportunity_pool: pool", today_source)
        self.assertNotIn("priority.score =", today_source)
        self.assertNotIn("priority: {", today_source)

    def test_today_private_state_indexes_fail_closed_instead_of_silently_truncating(self):
    source = (WEB_ROOT / "api" / "private.js").read_text(encoding="utf-8")
    start = source.index("async function todayFollowupMap")
    end = source.index("function hasActiveFollowup", start)
    index_source = source[start:end]
    self.assertEqual(index_source.count("LIMIT 5001"), 2)
    self.assertIn("TODAY_FOLLOWUP_INDEX_TRUNCATED", index_source)
    self.assertIn("TODAY_FEEDBACK_INDEX_TRUNCATED", index_source)
    self.assertNotIn("LIMIT 500\n", index_source)

    def test_attention_sort_is_stable_inside_each_feedback_tier(self):
        source = (WEB_ROOT / "api" / "private.js").read_text(encoding="utf-8")
        self.assertIn("left.tier - right.tier || left.index - right.index", source)


if __name__ == "__main__":
    unittest.main()
