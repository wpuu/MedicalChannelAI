from pathlib import Path
import unittest

from medical_channel_pipeline.ccgp_discovery import DiscoveryCandidate
from medical_channel_pipeline.regional_candidate import (
    NON_COMPETITIVE_SINGLE_SOURCE,
    OUT_OF_MEDICAL_SCOPE,
    regional_candidate_priority,
    regional_candidate_skip_reason,
)

PIPELINE_ROOT = Path(__file__).resolve().parents[1]


def candidate(title: str, *, buyer: str | None = None, notice_type: str | None = None) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        title=title,
        detail_url='https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/example.htm',
        published_at='2026-09-08',
        buyer_name=buyer,
        region='北京',
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

    def test_clear_administration_exclusions_are_skipped_before_detail(self):
        vehicle = candidate(
            '吉林省产品质量监督检验院班车和业务用车租赁服务（第一包）',
            buyer='吉林省产品质量监督检验院',
            notice_type='公开招标公告',
        )
        office = candidate(
            '某医院办公耗材采购项目公开招标公告',
            buyer='某医院',
            notice_type='公开招标公告',
        )
        self.assertEqual(regional_candidate_skip_reason(vehicle), OUT_OF_MEDICAL_SCOPE)
        self.assertEqual(regional_candidate_skip_reason(office), OUT_OF_MEDICAL_SCOPE)

    def test_sparse_but_clear_medical_titles_are_not_false_negative_skips(self):
        titles = [
            '中国医学科学院北京协和医院放射科乳腺机采购项目公开招标公告',
            '中日友好医院免散瞳眼底照相机系统采购项目公开招标公告',
            '中国疾病预防控制中心疾病预防控制专用设备购置项目公开招标公告',
            '国家卫生健康委统计信息中心2026年应用支撑平台、信息互通共享功能升级项目公开招标公告',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertIsNone(regional_candidate_skip_reason(candidate(title, notice_type='公开招标公告')))

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

    def test_detail_budget_prioritizes_sparse_medical_device_and_it_titles(self):
        metrology = candidate(
            '市计量院计量专业检验检测设备更新项目公开招标公告',
            buyer='北京市计量检测科学研究院',
            notice_type='公开招标公告',
        )
        publishing = candidate(
            '北京中医药大学东方医院办刊运营服务采购项目公开招标公告',
            buyer='北京中医药大学东方医院',
            notice_type='公开招标公告',
        )
        mammography = candidate(
            '中国医学科学院北京协和医院放射科乳腺机采购项目公开招标公告',
            buyer='中国医学科学院北京协和医院',
            notice_type='公开招标公告',
        )
        health_it = candidate(
            '国家卫生健康委统计信息中心应用支撑平台、信息互通共享功能升级项目公开招标公告',
            notice_type='公开招标公告',
        )
        self.assertGreater(regional_candidate_priority(mammography), regional_candidate_priority(metrology))
        self.assertGreater(regional_candidate_priority(health_it), regional_candidate_priority(publishing))

    def test_regional_sync_classifies_and_prioritizes_before_detail_budget(self):
        source = (PIPELINE_ROOT / 'scripts/sync_regional_ccgp.py').read_text(encoding='utf-8')
        classifier_at = source.index('regional_candidate_skip_reason(candidate)')
        priority_at = source.index('regional_candidate_priority(item[1])')
        detail_at = source.index('fetch_ccgp_detail_html(candidate.detail_url)')
        self.assertLess(classifier_at, priority_at)
        self.assertLess(priority_at, detail_at)
        self.assertIn("'candidate_prefilter_only_rejects_explicit_exclusions': True", source)
        self.assertIn("'candidate_detail_budget_uses_recall_preserving_priority': True", source)


if __name__ == '__main__':
    unittest.main()
