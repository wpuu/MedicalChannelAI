from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class TargetHospitalModelTests(unittest.TestCase):
    def test_target_hospitals_are_separate_from_relationships(self):
        schema = (WEB_ROOT / 'api' / '_privateDb.js').read_text(encoding='utf-8')
        profile = (WEB_ROOT / 'api' / 'profile.js').read_text(encoding='utf-8')
        export = (WEB_ROOT / 'api' / 'auth.js').read_text(encoding='utf-8')
        doc = (WEB_ROOT.parent / 'docs' / 'project' / 'TARGET_HOSPITAL_MODEL.md').read_text(encoding='utf-8')

        self.assertIn('private_target_hospitals', schema)
        self.assertIn('target_hospitals', profile)
        self.assertIn('private_target_hospitals', profile)
        self.assertIn('target_hospitals', export)
        self.assertIn('private_target_hospitals', export)
        self.assertIn('目标医院不计入 `RELATIONSHIP` 分数', doc)

    def test_target_profile_write_is_backward_compatible(self):
        profile = (WEB_ROOT / 'api' / 'profile.js').read_text(encoding='utf-8')
        self.assertIn("const targetHospitalsProvided = Object.prototype.hasOwnProperty.call(body, 'target_hospitals')", profile)
        self.assertIn('target_hospitals: targetHospitalsProvided ? targetHospitals : null', profile)
        self.assertIn('if (profile.target_hospitals !== null)', profile)

    def test_clear_profile_deletes_targets_independently(self):
        profile = (WEB_ROOT / 'api' / 'profile.js').read_text(encoding='utf-8')
        delete_start = profile.index("if (request.method === 'DELETE')")
        delete_end = profile.index('const profile = validateProfile', delete_start)
        delete_source = profile[delete_start:delete_end]
        self.assertIn('DELETE FROM private_target_hospitals', delete_source)
        self.assertIn('DELETE FROM private_hospital_relationships', delete_source)


if __name__ == '__main__':
    unittest.main()
