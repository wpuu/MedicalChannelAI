# Evidence pipeline

This directory is the first executable fact layer for MedicalChannelAI.

It intentionally has no model dependency. Critical procurement facts are accepted only when the input record carries provenance to an allowed official source. Customer-private relationships and product resources are not part of this seed layer.

## Validate and test

```bash
cd pipeline
python -m unittest discover -s tests -v
```

The last confirmed local run predates some of the newest CCGP-detail/event and AI-boundary changes. Do not claim the newer regressions PASS until they have executable evidence. Repository CI is currently blocked because GitHub Actions has not assigned a runner.

## Build a unified H5-safe Tianjin snapshot

```bash
cd pipeline
python scripts/build_public_snapshot.py \
  --input data/tianjin_verified_seed.json \
  --input data/tianjin_official_institution_seed.json \
  --event-input data/tianjin_notice_events.json \
  --output out/today-actions.public.json \
  --as-of 2026-08-31T17:56:00+08:00
```

To update the static verified web trial directly:

```bash
cd pipeline
python scripts/publish_web_snapshot.py \
  --as-of 2026-08-31T17:56:00+08:00
```

The generated object follows the public boundary consumed by `web/` and contains no provider, upstream model, API key or internal task payload.

The current two official source classes are:

- China Government Procurement Network procurement notices;
- official hospital market-research / pre-procurement notices.

## Source stages

CCGP search results are `DISCOVERY_ONLY`. Search-list metadata never upgrades a record to `VERIFIED` by itself. A canonical record must carry accepted official evidence for every non-empty critical fact.

For one known CCGP detail URL:

```bash
cd pipeline
python scripts/verify_ccgp_url.py \
  --url 'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/...' \
  --output out/verified-record.json
```

The verified-detail parser fails closed if it cannot determine required public-tender timing fields such as the exact file-acquisition cutoff.

## Low-frequency Pilot sync

`sync_ccgp_query.py` connects the current CCGP layers without bypassing rate limits:

```bash
cd pipeline
python scripts/sync_ccgp_query.py \
  --keyword '医疗设备' \
  --start-date 2026-08-30 \
  --end-date 2026-08-31 \
  --max-candidates 5 \
  --delay-seconds 4 \
  --records-output out/live-records.json \
  --events-output out/live-events.json \
  --report-output out/live-report.json
```

Flow:

`public search -> DISCOVERY_ONLY -> official detail -> VERIFIED record -> correction/termination scan -> report`

Rules:

- detail verification failure never upgrades a candidate to VERIFIED;
- request delay may not be set below 3 seconds;
- an unreconciled official correction notice suppresses the stale original project from Today Actions;
- an official termination notice suppresses the terminated project;
- event-detail failure may conservatively suppress an old card based on the official discovery result, but it may not rewrite procurement facts;
- failures are written to the sync report instead of being silently ignored.

## Current boundary

The Tianjin site is still a controlled verified snapshot, not a fully scheduled production collector. `production_ready=false` until live collection, current-detail verification, event reconciliation, executable regression evidence and Preview runtime validation are complete.
