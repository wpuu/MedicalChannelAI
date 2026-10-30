import { readFileSync } from 'node:fs'
import { validateVerifiedSnapshot } from '../api/_verifiedSnapshot.js'

const snapshot = JSON.parse(
  readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'),
)
const withWitness = structuredClone(snapshot)
if (!withWitness.collection_coverage) {
  withWitness.collection_coverage = {
    complete: false,
    last_complete_as_of: null,
    updated_source_ids: [],
    failed_source_ids: [],
  }
}
withWitness.collection_coverage.collector_source_witness = {
  schema_version: '0.1',
  cycle_id: 'prod:2026-10-30:morning:twice-daily-v1',
  trigger_accepted_at: '2026-10-30T00:35:00+00:00',
  witnessed_stage_count: 22,
  witness_sha256: 'a'.repeat(64),
  source_quality: 'NO_STAGE_FAILURES_REPORTED',
  attestation_level: 'CACHE_EVENTS_OBSERVED_BEFORE_DURABLE_PUBLISH',
}

// Validate the actual source-of-truth public snapshot schema without changing
// its runtime rules. This witness is a bounded, optional field of the *same*
// document that gets persisted as the entire durable snapshot JSONB payload.
validateVerifiedSnapshot(withWitness)

const injected = structuredClone(withWitness)
injected.collection_coverage.collector_source_witness.api_key = 'must-not-leak'
let rejected = false
try {
  validateVerifiedSnapshot(injected)
} catch (error) {
  rejected = String(error?.message || '').startsWith('VERIFIED_SNAPSHOT_INTERNAL_FIELD:')
}
if (!rejected) throw new Error('COLLECTOR_WITNESS_PUBLIC_SECRET_BOUNDARY_NOT_ENFORCED')

if (typeof withWitness.collection_coverage.collector_source_witness.witness_sha256 !== 'string') {
  throw new Error('COLLECTOR_WITNESS_HASH_MISSING')
}

console.log('Collector proof within durable/public snapshot contract: PASS')
