from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
PROFILE_API = WEB_ROOT / 'api' / 'profile.js'
PRIVATE_CONTEXT = WEB_ROOT / 'api' / '_privateProfileContext.js'
AI_ANALYZE = WEB_ROOT / 'api' / 'ai' / 'analyze.js'


class LegacyDirectCapabilityTests(unittest.TestCase):
    def test_profile_api_accepts_but_normalizes_legacy_direct(self) -> None:
        source = PROFILE_API.read_text(encoding='utf-8')
        self.assertIn("'DIRECT',", source)
        self.assertIn("return value === 'DIRECT' ? 'DIRECT_UNCONFIRMED' : value", source)
        self.assertIn("CASE WHEN capability_type = 'DIRECT' THEN 'DIRECT_UNCONFIRMED'", source)

    def test_private_scoring_never_treats_legacy_direct_as_authorized(self) -> None:
        source = PRIVATE_CONTEXT.read_text(encoding='utf-8')
        self.assertIn("case 'DIRECT_AUTHORIZED': return 25", source)
        self.assertIn("case 'DIRECT':\n    case 'DIRECT_UNCONFIRMED': return 18", source)
        self.assertIn("CASE WHEN capability_type = 'DIRECT' THEN 'DIRECT_UNCONFIRMED'", source)
        self.assertNotIn("case 'DIRECT': return 25", source)

    def test_outreach_never_words_legacy_direct_as_authorized(self) -> None:
        source = AI_ANALYZE.read_text(encoding='utf-8')
        self.assertIn("if (type === 'DIRECT_AUTHORIZED')", source)
        self.assertIn("if (type === 'DIRECT' || type === 'DIRECT_UNCONFIRMED')", source)
        self.assertIn('我们正在确认${category}相关供货条件', source)
        self.assertNotIn("type === 'DIRECT_AUTHORIZED' || type === 'DIRECT'", source)


if __name__ == '__main__':
    unittest.main()
