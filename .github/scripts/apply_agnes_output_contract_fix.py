from pathlib import Path

root = Path(__file__).resolve().parents[2]
discover = root / 'web/api/ai/discover.js'
text = discover.read_text(encoding='utf-8')

old = """        max_candidates: 12,
        output_schema: {
          candidates: [{
            title: '对应输入标题',
            url: '必须与输入URL完全一致',
            signal_type: Array.from(SIGNAL_TYPES),
            confidence: '0到1',
            reason: '不超过80个汉字',
          }],
        },
"""

new = """        max_candidates: 12,
        allowed_signal_types: Array.from(SIGNAL_TYPES),
        output_rules: [
          'candidates只包含判断为采购前期窗口的链接',
          '每个candidate的signal_type必须是单个字符串，且只能取allowed_signal_types中的一个值',
          'confidence必须是0到1之间的数字',
          'reason不超过30个汉字',
          '不要返回title字段',
        ],
        output_schema: {
          candidates: [{
            url: '必须与输入URL完全一致',
            signal_type: '单个字符串枚举值',
            confidence: 0.95,
            reason: '不超过30个汉字',
          }],
        },
"""

if text.count(old) != 1:
    raise SystemExit(f'contract patch marker mismatch count={text.count(old)}')
text = text.replace(old, new)
discover.write_text(text, encoding='utf-8')

test_path = root / 'web/pipeline/tests/test_agnes_output_contract.py'
test_path.write_text("""import unittest
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

    def test_contract_fix_does_not_change_model_timeout_or_thinking_mode(self):
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.source)
        self.assertIn('const PROVIDER_TIMEOUT_MS = 12_000', self.source)
        self.assertNotIn('enable_thinking', self.source)
        self.assertNotIn('reasoning_effort', self.source)


if __name__ == '__main__':
    unittest.main()
""", encoding='utf-8')

print('Agnes output contract fix applied; regression test written.')
