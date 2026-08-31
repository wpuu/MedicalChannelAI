# Evidence pipeline

This directory is the first executable fact layer for MedicalChannelAI.

It intentionally has no model dependency. Critical procurement facts are accepted only when the input record carries provenance to an allowed official source. Customer-private relationships and product resources are not part of this seed layer.

## Validate and test

```bash
cd pipeline
python -m unittest discover -s tests -v
```

## Build an H5-safe snapshot

```bash
cd pipeline
python scripts/build_public_snapshot.py \
  --input data/tianjin_verified_seed.json \
  --output out/today-actions.public.json \
  --as-of 2026-08-31T16:42:00+08:00
```

The generated object follows the public boundary consumed by `web/src/services/ApiTodayActionsService.ts` and contains no provider, upstream model, API key or internal task payload.

## Important

The seed is a migration of the already verified Tianjin demo snapshot. It is not yet an automatic crawler. A CCGP adapter and an official hospital-site adapter are separate M1 gates.
