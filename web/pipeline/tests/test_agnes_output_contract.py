import unittest
from pathlib import Path


class AgnesOutputContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[2] / 'api/ai/discover.js').read_text(encoding='utf-8')

    def test_prompt_declares_signal_type_as_one_string_enum(self):
        self.assertIn('allowed_signal_types: Array.from(SIGNAL_TYPES)', self.source)
        self.assertIn("signal_type: '单个字符串枚举值'", self.source)
        self.assertIn('signal_type必须是单个字符串', self.source)
        self.assertNotIn('signal_type: Array.from(SIGNAL_TYPES)', self.source)

    def test_prompt_does_not_request_redundant_title_and_bounds_reason(self):
        self.assertNotIn("title: '对应输入标题'", self.source)
        self.assertIn("reason: '不超过30个汉字'", self.source)
        self.assertIn("'不要返回title字段'", self.source)

    def test_parser_contract_remains_single_string_and_grounded(self):
        self.assertIn("typeof row.signal_type === 'string'", self.source)
        self.assertIn('const anchor = allowed.get(rawUrl)', self.source)
        self.assertIn('if (!SIGNAL_TYPES.has(signalType)', self.source)

    def test_async_architecture_keeps_model_but_moves_latency_off_request_path(self):
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.source)
        self.assertIn('const BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000', self.source)
        self.assertIn('chat_template_kwargs: { enable_thinking: false }', self.source)
        self.assertIn('waitUntil(task)', self.source)
        self.assertNotIn('reasoning_effort', self.source)


if __name__ == '__main__':
    unittest.main()
