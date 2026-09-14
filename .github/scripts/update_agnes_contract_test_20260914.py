from pathlib import Path

path = Path('app/web/pipeline/tests/test_agnes_output_contract.py')
text = path.read_text(encoding='utf-8')
old = '''    def test_contract_fix_does_not_change_model_timeout_or_thinking_mode(self):
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.source)
        self.assertIn('const PROVIDER_TIMEOUT_MS = 12_000', self.source)
        self.assertNotIn('enable_thinking', self.source)
        self.assertNotIn('reasoning_effort', self.source)
'''
new = '''    def test_async_architecture_keeps_model_but_moves_latency_off_request_path(self):
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.source)
        self.assertIn('const BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000', self.source)
        self.assertIn('chat_template_kwargs: { enable_thinking: false }', self.source)
        self.assertIn('waitUntil(task)', self.source)
        self.assertNotIn('reasoning_effort', self.source)
'''
if text.count(old) != 1:
    raise SystemExit(f'expected old contract guard once, found {text.count(old)}')
path.write_text(text.replace(old, new), encoding='utf-8')
print('updated Agnes output-contract architecture guard')
