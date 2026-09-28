from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class TargetHospitalOperatingViewTests(unittest.TestCase):
    def test_target_operating_view_is_routable_without_new_backend_function(self):
        app = (WEB_ROOT / 'src' / 'App.tsx').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'TargetHospitalsPage.tsx').read_text(encoding='utf-8')
        self.assertIn("path=\"/targets\"", app)
        self.assertIn('TargetHospitalsPage', app)
        self.assertIn('loadCustomerProfile()', page)
        # Target matching needs the full verified pool (not only the 5 Today
        # cards); hydrateFollowups:false selects the pool endpoint in API mode.
        self.assertIn('todayActionsService.getTodayActions({ hydrateFollowups: false })', page)
        self.assertNotIn('/api/targets', page)

    def test_target_view_keeps_focus_relationship_and_public_channel_distinct(self):
        page = (WEB_ROOT / 'src' / 'pages' / 'TargetHospitalsPage.tsx').read_text(encoding='utf-8')
        self.assertIn('目标医院本身不会增加医院关系分', page)
        self.assertIn('院内关系：尚未确认', page)
        self.assertIn('目标医院名称不会自动推导官网地址', page)
        self.assertIn('配置公开渠道', page)
        self.assertIn("to=\"/radar\"", page)
        self.assertIn("to=\"/resources\"", page)

    def test_target_view_keeps_zero_opportunity_targets_visible(self):
        page = (WEB_ROOT / 'src' / 'pages' / 'TargetHospitalsPage.tsx').read_text(encoding='utf-8')
        self.assertIn('当前已核验公开商机池中暂无可行动机会', page)
        self.assertIn('继续关注，不代表其他尚未覆盖的公开来源一定没有信息', page)
        self.assertIn('targetMatchesOpportunity', page)
        self.assertIn('targetRows.map', page)

    def test_mobile_navigation_promotes_targets_without_six_primary_tabs(self):
        layout = (WEB_ROOT / 'src' / 'components' / 'layout' / 'AppLayout.tsx').read_text(encoding='utf-8')
        mobile = layout[layout.index('<nav className="fixed inset-x-0 bottom-0'):]
        self.assertIn('to="/targets"', mobile)
        self.assertIn('<span>目标</span>', mobile)
        self.assertNotIn('to="/opportunities"', mobile)
        self.assertIn('to="/resources"', mobile)


if __name__ == '__main__':
    unittest.main()
