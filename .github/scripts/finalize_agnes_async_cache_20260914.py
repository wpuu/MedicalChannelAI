from pathlib import Path

root = Path('app')


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    path.write_text(text.replace(old, new), encoding='utf-8')


# Continuation durable ledger must accept the new v2 segment contract.
replace_once(
    root / 'web/src/services/discoveryContinuationLedger.ts',
    "    row.analysis_version !== 'agnes-discovery-continuation-v1' ||\n",
    "    row.analysis_version !== 'agnes-discovery-continuation-v2' ||\n",
    'continuation ledger version',
)

# A force-AI request is a replacement analysis, never an additive merge with old cache rows.
replace_once(
    root / 'web/api/ai/discover.js',
    "    const baseParsed = previous?.reusedParsed || (cached?.state === 'READY' ? cached.parsed : emptyParsed())\n",
    "    const baseParsed = body?.force_ai === true\n      ? emptyParsed()\n      : previous?.reusedParsed || (cached?.state === 'READY' ? cached.parsed : emptyParsed())\n",
    'force AI cache replacement',
)

# Add regression guards for both issues caught by staged TypeScript review.
path = root / 'web/pipeline/tests/test_agnes_async_cache.py'
text = path.read_text(encoding='utf-8')
marker = "    def test_multi_scan_does_not_spawn_client_poll_storm(self) -> None:\n"
insert = '''    def test_force_ai_replaces_instead_of_merging_ready_cache(self) -> None:
        self.assertIn("const baseParsed = body?.force_ai === true", self.root)
        self.assertIn("? emptyParsed()", self.root)

    def test_continuation_ledger_accepts_v2_segments(self) -> None:
        ledger = (WEB_ROOT / 'src' / 'services' / 'discoveryContinuationLedger.ts').read_text(encoding='utf-8')
        self.assertIn("row.analysis_version !== 'agnes-discovery-continuation-v2'", ledger)
        self.assertNotIn("row.analysis_version !== 'agnes-discovery-continuation-v1'", ledger)

'''
if text.count(marker) != 1:
    raise SystemExit(f'async test marker expected once, found {text.count(marker)}')
path.write_text(text.replace(marker, insert + marker), encoding='utf-8')
print('final async-cache fixes prepared')
