from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
PROFILE_API = WEB_ROOT / 'api' / 'profile.js'
PRIVATE_CONTEXT = WEB_ROOT / 'api' / '_privateProfileContext.js'


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


if __name__ == '__main__':
    unittest.main()
