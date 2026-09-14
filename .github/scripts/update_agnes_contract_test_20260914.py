from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    path.write_text(text.replace(old, new), encoding='utf-8')


path = Path('app/web/pipeline/tests/test_agnes_output_contract.py')
replace_once(
    path,
    '''    def test_contract_fix_does_not_change_model_timeout_or_thinking_mode(self):
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.source)
        self.assertIn('const PROVIDER_TIMEOUT_MS = 12_000', self.source)
        self.assertNotIn('enable_thinking', self.source)
        self.assertNotIn('reasoning_effort', self.source)
''',
    '''    def test_async_architecture_keeps_model_but_moves_latency_off_request_path(self):
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.source)
        self.assertIn('const BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000', self.source)
        self.assertIn('chat_template_kwargs: { enable_thinking: false }', self.source)
        self.assertIn('waitUntil(task)', self.source)
        self.assertNotIn('reasoning_effort', self.source)
''',
    'Agnes output contract guard',
)

path = Path('app/web/pipeline/tests/test_ai_discovery_radar_contract.py')
replace_once(
    path,
    "        self.assertIn('PROVIDER_TIMEOUT_MS = 12_000', endpoint)\n",
    "        self.assertIn('BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000', endpoint)\n"
    "        self.assertIn('waitUntil(task)', endpoint)\n"
    "        self.assertIn(\"chat_template_kwargs: { enable_thinking: false }\", endpoint)\n",
    'radar async cost guard',
)

path = Path('app/web/pipeline/tests/test_discovery_continuation_contract.py')
replace_once(
    path,
    "        self.assertIn(\"body?.analysis_version === 'agnes-discovery-continuation-v1'\", self.client)\n",
    "        self.assertIn(\"body?.analysis_version === 'agnes-discovery-continuation-v2'\", self.client)\n",
    'continuation version guard',
)

print('updated Agnes architecture regression guards')
