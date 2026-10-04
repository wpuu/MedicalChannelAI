# PR77 narrow mixed-currency header correction

Remote baseline: `c5ac829c3f4ccd1a11a2c9de509667864bfc80a4`, tree
`a1d0735a9686c150156e509fca14896323b17084`; local `66099607…` has that tree.

The parser previously accepted `10元` under `单价美元(元)` because the
parenthesized 元 overrode the contradictory outer currency. It now rejects
unsupported currency tokens across the complete header before resolving CNY
units. 人民币元/人民币万元 remain CNY spelling variants, not extra currency
support. Explicit body units cannot override a conflicting header.

Three new tests cover 美元(元), 欧元(元), 人民币(美元), 美元(人民币元), USD(元),
港元(万元), each with bare/元/万元 bodies; normal 元/万元/人民币 forms and scale
conflicts; actual award-price and package projections retaining no mixed-header
amounts. Before the fix: 3 tests, 12 failing assertions. After the fix, at
2026-10-04 03:31:51 UTC: 32 relevant parser/price-projection tests PASS.

Actual command, cwd `web/pipeline`:

```bash
PYTHONPATH=.:tests:/tmp/medical-pr74-offline python3 -m unittest test_ccgp_award test_award_price_reference test_pr74_evidence_boundaries.EvidenceBoundaryRegressionTests.test_mixed_currency_headers_are_unknown_even_with_explicit_cny_body test_pr74_evidence_boundaries.EvidenceBoundaryRegressionTests.test_normal_cny_headers_keep_explicit_currency_and_scale test_pr74_evidence_boundaries.EvidenceBoundaryRegressionTests.test_mixed_currency_headers_never_enter_price_or_package_projection
```

The red run used the same three new fully qualified test names alone before
changing the parser. Logs: [evidence/PR77-MIXED-HEADER-20261004](evidence/PR77-MIXED-HEADER-20261004/).

The existing PR77 read regression is now an unconditional top-level
`await import('./check-pr77-read-evidence.mjs')` in normal `run-prebuild.mjs`,
immediately after the PR74 regression. No skip flag or workflow change was added.
At 03:33:13 UTC, `node --check scripts/run-prebuild.mjs` and a TypeScript AST
check verified its single unconditional awaited import and exact position.

**The complete prebuild entry was not executed this round**, because it would
repeat the full Python suite. The PR77 read regression's prior standalone PASS
remains the runtime evidence; this round checks its integration only, not a new
pass through the complete entry. No 62/865 suite, four-source/UI rerun, bundle
refresh, collection, DB/cache/schema, model, queue, CI dispatch, merge or deployment.

Only the same isolated Draft PR77 code/evidence is saved. Its title/description
update was previously denied by automatic approval review and is not retried.
Independent point review and production/runtime acceptance remain separate.
