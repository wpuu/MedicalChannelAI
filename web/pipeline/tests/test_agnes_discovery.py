from __future__ import annotations

import json
import unittest

from medical_channel_pipeline.agnes_discovery import (
    OfficialAnchor,
    build_agnes_discovery_messages,
    discovery_benchmark_metrics,
    extract_official_anchors,
    parse_agnes_discovery_content,
)


class AgnesDiscoveryTests(unittest.TestCase):
    def test_anchor_extraction_keeps_only_grounded_official_hosts(self):
        html = '''
        <a href="/a/1">需求调研</a>
        <a href="https://evil.example/x">外站</a>
        <a href="/a/1#fragment">重复</a>
        <a href="javascript:void(0)">脚本</a>
        '''
        anchors = extract_official_anchors(
            html,
            base_url="https://hospital.example/index.html",
            allowed_hosts={"hospital.example"},
        )
        self.assertEqual([item.url for item in anchors], ["https://hospital.example/a/1"])
        self.assertEqual(anchors[0].title, "需求调研")

    def test_prompt_explicitly_excludes_formal_and_result_notices(self):
        messages = build_agnes_discovery_messages(
            source_name="测试医院",
            anchors=[OfficialAnchor(title="某设备需求调研", url="https://hospital.example/a/1")],
        )
        system = messages[0]["content"]
        self.assertIn("需求调研", system)
        self.assertIn("正式招标公告", system)
        self.assertIn("成交/中标结果", system)
        self.assertIn("禁止补全、改写或猜测URL", system)

    def test_parser_rejects_model_invented_url_and_invalid_rows(self):
        allowed = [OfficialAnchor(title="某设备需求调研", url="https://hospital.example/a/1")]
        content = json.dumps(
            {
                "candidates": [
                    {
                        "title": "某设备需求调研",
                        "url": "https://hospital.example/a/1",
                        "signal_type": "DEMAND_RESEARCH",
                        "confidence": 0.92,
                        "reason": "处于需求调研阶段",
                    },
                    {
                        "title": "模型编造",
                        "url": "https://hospital.example/a/999",
                        "signal_type": "DEMAND_RESEARCH",
                        "confidence": 0.99,
                        "reason": "不存在",
                    },
                    {
                        "title": "坏类型",
                        "url": "https://hospital.example/a/1",
                        "signal_type": "FORMAL_BID",
                        "confidence": 0.5,
                        "reason": "应被拒绝",
                    },
                ]
            },
            ensure_ascii=False,
        )
        result = parse_agnes_discovery_content(content, allowed_anchors=allowed)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.rejected_ungrounded_count, 1)
        self.assertEqual(result.rejected_invalid_count, 1)

    def test_benchmark_score_rewards_known_recall_and_grounding(self):
        allowed = [
            OfficialAnchor(title="A", url="https://hospital.example/a"),
            OfficialAnchor(title="B", url="https://hospital.example/b"),
        ]
        parsed = parse_agnes_discovery_content(
            json.dumps(
                {
                    "candidates": [
                        {
                            "title": "A",
                            "url": "https://hospital.example/a",
                            "signal_type": "DEMAND_RESEARCH",
                            "confidence": 0.9,
                            "reason": "需求调研",
                        },
                        {
                            "title": "B",
                            "url": "https://hospital.example/b",
                            "signal_type": "SUPPLIER_RECRUITMENT",
                            "confidence": 0.8,
                            "reason": "供应商征集",
                        },
                    ]
                }
            ),
            allowed_anchors=allowed,
        )
        metrics = discovery_benchmark_metrics(
            [parsed],
            gold_urls={"https://hospital.example/a", "https://hospital.example/b"},
        )
        self.assertEqual(metrics["known_recall"], 1.0)
        self.assertEqual(metrics["grounded_rate"], 1.0)
        self.assertEqual(metrics["discovery_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
