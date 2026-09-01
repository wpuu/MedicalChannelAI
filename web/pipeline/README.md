# Evidence pipeline

This directory is the executable fact layer for MedicalChannelAI and now lives inside the Vercel `web/` project boundary so the same verified pipeline can be reused by production Python Functions and durable refresh jobs.

It intentionally has no model dependency. Critical procurement facts are accepted only when the input record carries provenance to an allowed official source. Customer-private relationships and product resources are not part of this fact layer.

## Validate and test

From the repository root:

```bash
cd web/pipeline
python -m unittest discover -s tests -v
```

Vercel's `web/scripts/run-prebuild.mjs` executes this suite before each production build.

## Build a unified H5-safe Tianjin snapshot

```bash
cd web/pipeline
python scripts/build_public_snapshot.py \
  --input data/tianjin_verified_seed.json \
  --input data/tianjin_official_institution_seed.json \
  --event-input data/tianjin_notice_events.json \
  --output out/today-actions.public.json \
  --as-of 2026-08-31T17:56:00+08:00
```

To update the bundled verified web trial directly:

```bash
cd web/pipeline
python scripts/publish_web_snapshot.py \
  --as-of 2026-08-31T17:56:00+08:00
```

The generated object follows the public boundary consumed by `web/` and contains no provider, upstream model, API key or internal task payload.

## Source stages

CCGP search results are `DISCOVERY_ONLY`. Search-list metadata never upgrades a record to `VERIFIED` by itself. A canonical record must carry accepted official evidence for every non-empty critical fact.

The low-frequency sync remains fail-closed: detail verification failures never become VERIFIED facts, request delays may not be set below the source policy minimum, unreconciled correction notices suppress stale opportunities, and termination notices suppress terminated projects.

## Production boundary

The Vercel web application, grounded AI API and evidence pipeline now share one project boundary. `production_ready=false` remains intentional until the scheduled live collector and durable latest-snapshot storage are independently validated in Production.
