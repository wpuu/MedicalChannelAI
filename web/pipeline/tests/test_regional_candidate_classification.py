from pathlib import Path
import unittest

from web.pipeline.medical_channel_pipeline.ccgp_discovery import DiscoveryCandidate
from web.pipeline.medical_channel_pipeline.regional_candidate import (
    NON_COMPETITIVE_SINGLE_SOURCE,
    OUT_OF_MEDICAL_SCOPE,
    regional_candidate_skip_reason,
)

ROOT = Path(__file__).resolve().parents[2]


def candidate(title: str, *, buyer: str | None = None, notice_type: str | None = None) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        title=title,
        detail_url='https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/example.htm',
        published_at='2026-09-08',
        buyer_name=buyer,
        region='黑龙江',
        notice_type=notice_type,
        search_keyword='医疗',
    )


class RegionalCandidateClassificationTests(unittest.TestCase):
    def test_medical_competitive_notice_remains_actionable(self):
        item = candidate(
            '佳木斯大学附属第一医院低速冷冻离心机、血细胞分析仪等医疗设备采购项目竞争性磋商公告',
            buyer='佳木斯大学附属第一医院',
            notice_type='竞争性磋商公告',
        )
        self.assertIsNone(regional_candidate_skip_reason(item))

    def test_bus_and_business_vehicle_rental_is_out_of_medical_scope(self):
        item = candidate(
            '吉林省产品质量监督检验院班车和业务用车租赁服务（第一包）',
            buyer='吉林省产品质量监督检验院',
            notice_type='公开招标公告',
        )
        self.assertEqual(regional_candidate_skip_reason(item), OUT_OF_MEDICAL_SCOPE)

    def test_medical_single_source_publicity_is_non_competitive(self):
        item = candidate(
            '黑龙江省卫生健康管理服务评价中心2027年度全血细胞计数采购实行单一来源采购方式的公示',
            buyer='黑龙江省卫生健康管理服务评价中心',
            notice_type='单一来源公告',
        )
        self.assertEqual(regional_candidate_skip_reason(item), NON_COMPETITIVE_SINGLE_SOURCE)

    def test_search_query_type_cannot_override_single_source_title(self):
        item = candidate(
            '牡丹江市中心血站全自动血细胞分离机配套管路采购实行单一来源采购方式的公示',
            buyer='牡丹江市中心血站',
            notice_type='公开招标公告',
        )
        self.assertEqual(regional_candidate_skip_reason(item), NON_COMPETITIVE_SINGLE_SOURCE)

    def test_regional_sync_classifies_before_fetching_detail(self):
        source = (ROOT / 'scripts/sync_regional_ccgp.py').read_text(encoding='utf-8')
        classifier_at = source.index('regional_candidate_skip_reason(candidate)')
        detail_at = source.index('fetch_ccgp_detail_html(candidate.detail_url)')
        self.assertLess(classifier_at, detail_at)
        self.assertIn("'skipped_candidate_count': len(market_skips[code])", source)
        self.assertIn("'skipped_candidates': sorted(market_skips[code].values()", source)


if __name__ == '__main__':
    unittest.main()
