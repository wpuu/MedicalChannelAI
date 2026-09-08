from pathlib import Path

path = Path(__file__).resolve().with_name('preview_patch_business_markets.py')
text = path.read_text(encoding='utf-8')
old = '''patch(\n    "web/src/pages/ProcurementIntentFollowupPage.tsx",\n    "    setCards(data.opportunity_pool ?? data.cards)",\n    "    setCards(filterCardsByBusinessMarkets(data.opportunity_pool ?? data.cards))",\n)\npatch(\n    "web/src/pages/ProcurementIntentFollowupPage.tsx",\n    "        setCards(data.opportunity_pool ?? data.cards)",\n    "        setCards(filterCardsByBusinessMarkets(data.opportunity_pool ?? data.cards))",\n)\n'''
new = '''patch(\n    "web/src/pages/ProcurementIntentFollowupPage.tsx",\n    "    setCards(data.opportunity_pool ?? data.cards)",\n    "    setCards(filterCardsByBusinessMarkets(data.opportunity_pool ?? data.cards))",\n    expected=2,\n)\n'''
if text.count(old) != 1:
    raise SystemExit('FIX_PATCH_SCRIPT_TARGET_NOT_UNIQUE')
path.write_text(text.replace(old, new), encoding='utf-8')
print('one-shot patch script corrected')
