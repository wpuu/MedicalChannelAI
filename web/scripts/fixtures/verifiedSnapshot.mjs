import bundled from '../../public/data/today-actions.public.json' with { type: 'json' }
import { REQUIRED_SOURCE_IDS, SOURCE_STALE_AFTER_SECONDS } from '../../api/_sourceHealth.js'

// The clock follows the versioned fixture, never the date on the build host.
export const SNAPSHOT_TEST_NOW_MS = Date.parse(bundled.snapshot_as_of) + 60 * 60 * 1000

export function healthySourceMetadata(nowMs = SNAPSHOT_TEST_NOW_MS) {
  return {
    schema_version: '0.1',
    required_source_ids: [...REQUIRED_SOURCE_IDS],
    sources: Object.fromEntries(REQUIRED_SOURCE_IDS.map((id) => [id, {
      last_successful_scan_at: new Date(nowMs).toISOString(),
      last_attempt_at: new Date(nowMs).toISOString(),
      stale_after_seconds: SOURCE_STALE_AFTER_SECONDS[id],
      failure_reason: null,
    }])),
  }
}

export function makeVerifiedSnapshot({ asOfMs = SNAPSHOT_TEST_NOW_MS, ids = ['ccgp_tj_p0_fixture'] } = {}) {
  const snapshot = structuredClone(bundled)
  const template = bundled.cards[0] || bundled.opportunity_pool[0]
  const pool = ids.map((id, index) => ({
    ...structuredClone(template),
    opportunity_id: id,
    source_id: 'ccgp',
    rank: index + 1,
    facts: {
      ...structuredClone(template.facts),
      published_at: new Date(SNAPSHOT_TEST_NOW_MS - 60 * 60 * 1000).toISOString(),
      lifecycle_state: 'BIDDING',
      registration_deadline: new Date(SNAPSHOT_TEST_NOW_MS + 24 * 60 * 60 * 1000).toISOString(),
      registration_deadline_date: null,
      bid_deadline: new Date(SNAPSHOT_TEST_NOW_MS + 48 * 60 * 60 * 1000).toISOString(),
      quality_flags: [],
    },
  }))
  return {
    ...snapshot,
    snapshot_as_of: new Date(asOfMs).toISOString(),
    source_health: healthySourceMetadata(),
    cards: pool.slice(0, 5),
    card_count: Math.min(pool.length, 5),
    opportunity_pool: pool,
    opportunity_pool_count: pool.length,
    matched_count: pool.length,
    input_candidate_count: pool.length,
  }
}

export function installSnapshotTestClock(nowMs = SNAPSHOT_TEST_NOW_MS) {
  const OriginalDate = globalThis.Date
  globalThis.Date = class extends OriginalDate {
    constructor(...args) { super(...(args.length ? args : [nowMs])) }
    static now() { return nowMs }
  }
  return () => { globalThis.Date = OriginalDate }
}
