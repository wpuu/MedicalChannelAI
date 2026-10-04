# PR77 followed snapshot market propagation

Remote baseline: `e30694001e3dfb680b2fd66ad0f7292c457a008f`, tree
`5be344bf54ff0493003e6b1a7dd5f53da4b3a294`. Only the existing isolated Draft PR77
candidate is changed; Issue50 remains separate and untouched.

## Defect and correction

An existing verified source card contains `facts.market_code`, and the frontend
source adapter retains it. However, the server followup snapshot producer and
stored-snapshot sanitizer, local serializer/parser, followed-list projection,
and historical-card projections dropped the field. FollowedPage passes the
resulting missing market to the already strict project/market award matcher,
which correctly refuses to match. Thus newly followed known-market projects
could lose their matching scope before rendering an award notice.

The correction adds only the source market field to those projections. The API
facts validator accepts either its complete old exact shape or that shape plus
one nullable-string `market_code`; unrelated extra keys, missing required keys,
and malformed field types remain rejected. Stored local missing/invalid values
remain null. No inference from opportunity ID, region or buyer is added. Legacy
records without market still cannot match, and equal project numbers in different
markets do not substitute. No SQL statement, schema/protocol, matcher, UI caller,
workflow, deployment switch, or canonical public-data file changes.

## Actual offline regression

Cwd `/workspace/medical-pr74-evidence/web`:

```bash
node scripts/check-pr77-followed-market.mjs
```

The new regression runs the actual private followup POST/save JSON and followed
GET routes with memory SQL/authentication, the real API source adapter, strict
followed API reader and historical-card mapper, real localStorage serialization
and reload, and the existing matcher. Only boundary transports/configuration are
fixtures; followup persistence/projection is not replaced by identity functions.
Source/hospital/user values are labelled synthetic and no real customer data or
database is opened. A forged market in the POST body cannot override source facts.

Before correction: 2026-10-04 14:13:23.367409–14:13:25.040768 UTC, **8 cases /
6 failures**, exit 1. Final focused run: 14:15:35.893230–14:15:36.818705 UTC,
**8 cases PASS**, exit 0. Cases cover list/exact/history in both modes, explicit
null and old shape compatibility, malformed/extra/missing-key rejection, missing
market despite Tianjin-like ID/region/buyer, same-number different-market matching,
and reload without using a current source card to backfill market.

The gate is one unconditional awaited import directly after the existing PR77
read gate in `run-prebuild.mjs`.

## New aggregate build

An independent detached checkout at exact baseline e306940 received the five
candidate code/test files as an overlay. Its fingerprints were compared with the
candidate before and after running the original package build entry:

```bash
python3 /workspace/medical-pr74-evidence-review/pr77-final-build-harness/run-followed-market-build.py
# cwd /workspace/medical-pr77-final-build-20261004/web
# npm run build
# node scripts/run-prebuild.mjs && tsc --noEmit && vite build
```

At 14:16:22.919145–14:16:47.115088 UTC, exit 0: **872 Python tests**, all existing
prebuild gates and the new 8-case gate, TypeScript and Vite PASS. Vite took 4.97s.
The raw log identifies e306940 as the detached base; it does not imply that the
overlay had already been saved remotely. This is a new candidate build, distinct
from the earlier 07:35 baseline build and historical targeted evidence.

The minimal build environment contains no DB/provider/publish credentials. Existing
Python offline protection is reused with additional DNS protection, and Node
TCP/TLS/HTTP(S)/UDP/DNS/default-fetch transports are blocked underneath fixture
transports. Guard self-checks PASS; aggregate guard log contains zero events.
All 38 canonical JSON inputs and the bundled snapshot remain byte-identical. The
original snapshot clock remains `2026-09-29T00:43:40.252856+08:00`.

Logs: [evidence/PR77-FOLLOWED-MARKET-20261004](evidence/PR77-FOLLOWED-MARKET-20261004/).

## Review and limits

Separate static checks confirm every new line in the three business modules only
handles market_code, all backend SQL template strings are identical, and matcher,
FollowedPage, workflow and deployment config are unchanged. Independent parent
review of the final diff remains requested; the author does not claim a second
reviewer has accepted it.

No live DB/customer access, collection, provider call, queue operation, CI dispatch,
PR metadata update, merge or deployment. Existing records lacking market are not
reconstructed. Memory SQL is a boundary fixture, not actual Postgres/runtime
acceptance. An empty fixture queue or result does not establish production state.
