# PR77 incremental read-boundary correction

Baseline remote Draft PR77: `c408cda90f7cbc38da66c4270edcac20a29cd793`, tree
`d79d2323779004e281183d64effd4b4d009bb52a`. The local baseline `af6db417…`
has that same tree but different reconstruction history. Only the existing
`fix/pr74-evidence-boundaries-20261003` candidate is saved; the PR still targets
PR74's branch, with automatic deployment disabled. This is incremental review
evidence, not production acceptance.

## Behavior

- Server REMOTE, DATABASE (including the same bundled revision), RUNTIME_CACHE
  and BUNDLE reads, plus API/static browser reads, use one immutable projection
  in `web/shared/awardEvidence.js`. All card/pool/ledger legal windows remain
  UNKNOWN, with no derived anchor/deadline/countdown carried forward.
- Snapshot `award_projection_version=EXPLICIT_CNY_SCOPE_V1` attests the current
  producer's project-scope checks. A legacy snapshot with a positive retirement
  count is rejected. Server selection can use the independently rebuilt bundle;
  API/static clients reject such a legacy response. They never change its count
  to zero, invent missing opportunities, or mutate canonical/stored payloads.
- Ledger/price-row `projection_version` and per-field money basis are required:
  `total_amount_basis=VERIFIED_SUMMARY_TOTAL|VERIFIED_PACKAGE_SUM`, package
  `amount_basis=EXPLICIT_CNY`, and item/row `unit_price_basis=EXPLICIT_UNIT`.
  Old EXPLICIT_UNIT labels alone are insufficient. Unsupported money stays null;
  the visible wording is “金额待核验”. This is a trusted-producer projection
  contract, not a signature or independent proof of an arbitrary supplied marker.
- The CNY parser uses complete grammar: explicit 元/万元 (including the existing
  人民币 qualifier), valid comma groups, and consistent headers. Unsupported
  currency/scale, negative or percentage values, dangling parentheses and
  mixed/annotated amounts are rejected without heuristic conversion.
- Unit prices use only raw-verified package/total bounds. A raw 500元 / stored
  10000000 contradiction rejects the 1000元 unit price. A ceiling with no raw
  evidence is never used as proof. Existing raw source/evidence is retained.

The offline bundle retains its original clock `2026-09-29T00:43:40.252856+08:00`:
414 opportunities, 26 ledger entries, zero retired projects and zero historical
priced rows with sufficient raw evidence. Its only incremental diff is 89
metadata lines; no canonical record, source configuration, DB schema, cache
namespace, deployment switch or legal research was changed.

## Actual commands and results

Pipeline cwd: `/workspace/medical-pr74-evidence/web/pipeline`.

```bash
PYTHONPATH=.:tests:/tmp/medical-pr74-offline python3 -m unittest test_pr74_evidence_boundaries test_ccgp_award test_award_price_reference test_public_snapshot_awards test_published_web_snapshot test_snapshot_http_publish
PYTHONPATH=/tmp/medical-pr74-offline python3 scripts/refresh_bundled_snapshot.py
```

At 2026-10-04 03:03:55 UTC: **62 tests PASS**. The original `af6db417…` parser
was also loaded in memory using `git show` and replayed against the two new
independent counterexample tests: **6 failures**. No working files were reverted.
The captured initial JS red run has five failing read/API assertions.

Web cwd: `/workspace/medical-pr74-evidence/web`.

```bash
node scripts/check-pr77-read-evidence.mjs
node scripts/check-pr74-evidence-boundaries.mjs
node scripts/check-snapshot-client-dedupe.mjs
node scripts/check-legal-windows.mjs
node scripts/check-verified-snapshot.mjs
node scripts/check-snapshot-memo-and-prewarm.mjs
node_modules/.bin/tsc --noEmit
node_modules/.bin/vite build
git diff --check
```

The PR77 read script passed at 02:59:40 UTC: legacy rejected/unknown and normal
raw-evidenced total/package/unit prices across server lanes and API/static/pool
services. It uses actual loader/service code, memory DB/cache/HTTP stubs and
identity local customer/follow-up state; no production store is opened. The
other five JS checks passed. TypeScript and Vite build passed (build log
03:00:18 UTC). No repeated 62/865 suite, new install or CI run was used for save.

## Browser evidence

Existing installed Chromium/Playwright were used because agent-browser was
unavailable. The actual candidate services and React components run in the
clearly labelled local synthetic harness; source hashes are in the report.

```bash
/workspace/medical-pr74-evidence/web/node_modules/.bin/vite --configLoader native --config /workspace/scratch/pr77-ui-20261004/vite.config.mjs
node /workspace/scratch/pr77-ui-20261004/verify-browser.cjs
```

At 03:01:57 UTC: Chromium 151.0.7922.173, **375×812 and 1280×900 PASS**.
Compact/full/action/price navigation and filtering plus API-mode old evidence
are covered. API total/package/unit are null; card/pool/ledger windows UNKNOWN;
retired=4 legacy response rejected; both null-money components show 待核验.
No horizontal overflow, page/console errors or external requests. Ten screenshots
were saved and the two API screenshots were visually inspected. The harness
baseline identifier is the old remote commit; this run tested its local diff.

Logs, browser report, and the complete harness/fixtures/ten-screenshot ZIP are
in [evidence/PR77-READ-BOUNDARY-20261004](evidence/PR77-READ-BOUNDARY-20261004/).
The regression's small legacy snapshot fixture is a bounded copy of actual
PR74 JSON (first card/ledger/reference row, adjusted fixture list counts), keeping
998800 total/package, 55000 price, OPEN windows and retired=4. It is not a
newly fetched or complete production snapshot.

Library save failed with HTTP 401 before preparation; no Library IDs were
returned. The error is preserved; screenshot bytes are instead retained in the
candidate evidence ZIP. No credential or permission change was attempted.

## Remaining limits

No production DB/cache access, network collection, queue, model/customer data,
CI dispatch, merge or deployment. Real durable/cache/remote runtime behavior and
current-head deployment/browser acceptance remain unverified. Legal source
applicability, notice/supplier-specific anchors and whole-project completion
remain evidence gates. Historical canonical money without raw evidence remains
unknown until separately verified. Independent incremental review is pending.
