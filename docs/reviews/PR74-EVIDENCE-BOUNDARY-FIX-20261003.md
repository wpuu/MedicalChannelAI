# PR74 offline evidence boundary fixes

Source: PR #74 HEAD `e3c3ff27a3f4120bfcc36c8a05f291f63d03c081`, tree
`62ce258ecb70143fd10d2698b2e89f19fa6cb971`, independently read back from GitHub.
The isolated local snapshot `37e21de1641e366bfe5556c4b1649dcb9b7d3fc2` has exactly
that tree; it is a reconstruction commit, not the upstream commit identity.
Candidate branch: `fix/pr74-evidence-boundaries-20261003`.

## Result

- Missing/conflicting units produce unknown amounts. No domain-size heuristic
  and no automatic division by 10,000. Newly parsed records retain raw cells,
  headers, and their existing official source/evidence. Public projection rechecks
  units and bounds; legacy numeric values without raw evidence are suppressed.
- Publication of a package/result notice does not prove whole-project closure.
  Retirement now requires `project_completion_confirmed=true`, its own nonempty
  evidence locator on the same official notice, known market, and an AWARDED
  result. Existing adapters do not assert this new verified fact; no historical
  records were retroactively marked complete. Partial/failed results cannot retire
  a project. Result publication never removes projects from correction monitoring.
- Missing markets cannot match any market. Browser award linkage also requires
  the same known market. Followed responses lacking market metadata consequently
  receive no automatic award linkage; no private schema/migration was added.
- Legal windows and old derived countdowns remain UNKNOWN. Registration cutoff
  and result publication are insufficient legal anchors. Python, API, browser, and
  compact/full UI agree; disclaimers are visible text. Calendar/rule metadata is
  marked UNVERIFIED. No new legal rule or source-validity claim was introduced.

## Verification

Before implementation: 10 new regression tests produced 13 failing assertions.
Final regression file replayed against the exact upstream source tree:
13 tests, 16 failures; the same final file on the candidate: 13 tests PASS.
The additional failures cover whole-project evidence and missing-anchor cases.

Commands (pipeline cwd: `web/pipeline`; build cwd: `web`):

```bash
PYTHONPATH=/tmp/medical-pr74-offline python3 -m unittest discover -s tests -p test_pr74_evidence_boundaries.py -v
node scripts/check-pr74-evidence-boundaries.mjs
PYTHONPATH=/tmp/medical-pr74-offline npm run build
git diff --check
```

The offline `sitecustomize.py` raises `OFFLINE_TEST_NETWORK_BLOCKED` on Python
socket connect/create_connection; tests use captured fixtures and mocked services.
Build: 865 Python tests PASS, all prebuild checks PASS, TypeScript PASS, Vite PASS.
The JS regression executes the actual API/browser helpers, service logic with
fixture-only imports, and React SSR of both compact/full notices.
Dependencies used the existing lockfile and `npm ci --ignore-scripts --no-audit
--no-fund --cache /tmp/medical-pr74-npm-cache`; no lockfile change.

The bundled snapshot was rebuilt offline from existing tracked canonical files at
its original `snapshot_as_of`. Pool stays 414; retirement counter 4 -> 0; result
ledger stays 26; price-reference rows 51 -> 0. These are conservative evidence
suppression changes, not a fresh online collection. Compact JSON: 1,725,352 bytes.

## Release boundary and unknowns

Only this new branch is added to `web/vercel.json` with
`deploymentEnabled=false`; existing branches, cron/queue/runtime namespaces and
collector implementation are unchanged. A remote save must use this completed
tree and `[skip ci]`, with a draft targeting PR74's branch rather than main.
No merge, deployment, real collection/model call, Production/private DB access,
credential/permission change, new market, CI resource change, or Postgres protocol.

Official legal originals/current validity, applicable regime, supplier-specific
anchors, complete package inventory/project closure, and raw units for old stored
prices remain unverified. All affected projections fail closed pending separate
evidence review. This is a fix candidate for independent review, not release acceptance.
