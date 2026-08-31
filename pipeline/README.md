# Evidence pipeline

This directory is the first executable fact layer for MedicalChannelAI.

It intentionally has no model dependency. Critical procurement facts are accepted only when the input record carries provenance to an allowed official source. Customer-private relationships and product resources are not part of this seed layer.

## Validate and test

```bash
cd pipeline
python -m unittest discover -s tests -v
```

## Build a unified H5-safe Tianjin snapshot

```bash
cd pipeline
python scripts/build_public_snapshot.py \
  --input data/tianjin_verified_seed.json \
  --input data/tianjin_official_institution_seed.json \
  --output out/today-actions.public.json \
  --as-of 2026-08-31T16:42:00+08:00
```

The generated object follows the public boundary consumed by `web/src/services/ApiTodayActionsService.ts` and contains no provider, upstream model, API key or internal task payload.

The current two official source classes are:

- China Government Procurement Network procurement notices;
- official hospital market-research / pre-procurement notices.

## Source stages

CCGP search results are `DISCOVERY_ONLY`. Search-list metadata never upgrades a record to `VERIFIED` by itself. A canonical record must carry accepted official evidence for every non-empty critical fact.

The current Tianjin seed is still a controlled verified snapshot, not a fully scheduled production collector. `production_ready=false` until live collection, detail verification, deduplication, freshness and failure handling are validated end to end.
