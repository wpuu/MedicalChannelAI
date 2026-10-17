import { createHash } from 'node:crypto'
import { privateDatabaseConfigured, privateDb } from './_privateDb.js'

let schemaPromise = null

const PUBLIC_SCHEMA_KEY = 'medicalchannelai-public-intelligence'
const PUBLIC_SCHEMA_VERSION = '2026-09-27-public-intelligence-v2'
const PUBLIC_SCHEMA_LOCK_KEY = 'medicalchannelai-public-intelligence-schema-migration'

const PUBLIC_SCHEMA_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS public_schema_meta (
    schema_key text PRIMARY KEY,
    schema_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
  )`,
  `CREATE TABLE IF NOT EXISTS public_collector_runs (
    id TEXT PRIMARY KEY,
    region_code TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb
  )`,
  `CREATE INDEX IF NOT EXISTS public_collector_runs_region_started_idx
    ON public_collector_runs (region_code, started_at DESC)`,
  `CREATE TABLE IF NOT EXISTS public_opportunities (
    opportunity_id TEXT PRIMARY KEY,
    region_code TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    current_version INTEGER NOT NULL CHECK (current_version >= 1),
    current_fact_hash TEXT NOT NULL CHECK (length(current_fact_hash) = 64),
    current_payload JSONB NOT NULL,
    lifecycle_state TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_changed_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
  )`,
  `CREATE INDEX IF NOT EXISTS public_opportunities_region_state_idx
    ON public_opportunities (region_code, lifecycle_state, last_changed_at DESC)`,
  `CREATE TABLE IF NOT EXISTS public_opportunity_versions (
    opportunity_id TEXT NOT NULL REFERENCES public_opportunities(opportunity_id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version >= 1),
    fact_hash TEXT NOT NULL CHECK (length(fact_hash) = 64),
    payload JSONB NOT NULL,
    changed_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL,
    collector_run_id TEXT REFERENCES public_collector_runs(id) ON DELETE SET NULL,
    PRIMARY KEY (opportunity_id, version),
    UNIQUE (opportunity_id, fact_hash)
  )`,
  `CREATE INDEX IF NOT EXISTS public_opportunity_versions_observed_idx
    ON public_opportunity_versions (opportunity_id, observed_at DESC)`,
  `CREATE TABLE IF NOT EXISTS public_snapshot_materializations (
    region_code TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL CHECK (length(snapshot_hash) = 64),
    snapshot_as_of TIMESTAMPTZ NOT NULL,
    opportunity_count INTEGER NOT NULL CHECK (opportunity_count >= 0),
    materialized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (region_code, snapshot_hash)
  )`,
  `CREATE INDEX IF NOT EXISTS public_snapshot_materializations_region_time_idx
    ON public_snapshot_materializations (region_code, snapshot_as_of DESC)`,
  `CREATE TABLE IF NOT EXISTS public_verified_snapshots (
    snapshot_hash TEXT PRIMARY KEY CHECK (length(snapshot_hash) = 64),
    snapshot_as_of TIMESTAMPTZ NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    opportunity_count INTEGER NOT NULL CHECK (opportunity_count >= 0),
    materialized_at TIMESTAMPTZ NOT NULL DEFAULT now()
  )`,
  `CREATE INDEX IF NOT EXISTS public_verified_snapshots_as_of_idx
    ON public_verified_snapshots (snapshot_as_of DESC, materialized_at DESC)`,
  `CREATE TABLE IF NOT EXISTS public_ai_briefs (
    opportunity_id TEXT NOT NULL,
    fact_hash TEXT NOT NULL CHECK (length(fact_hash) = 64),
    window_state TEXT NOT NULL,
    brief_type TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    result JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (opportunity_id, fact_hash, window_state, brief_type, prompt_version)
  )`,
  `ALTER TABLE public_ai_briefs DROP CONSTRAINT IF EXISTS public_ai_briefs_opportunity_id_fkey`,
  `CREATE INDEX IF NOT EXISTS public_ai_briefs_lookup_idx
    ON public_ai_briefs (opportunity_id, fact_hash, generated_at DESC)`,
]

export function publicIntelligenceDatabaseConfigured() {
  return privateDatabaseConfigured()
}

export function publicIntelligenceDb() {
  return privateDb()
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize)
  const record = asObject(value)
  if (!record) return value
  const result = {}
  for (const key of Object.keys(record).sort()) result[key] = canonicalize(record[key])
  return result
}

function stableJson(value) {
  return JSON.stringify(canonicalize(value))
}

function sha256Json(value) {
  return createHash('sha256').update(stableJson(value), 'utf8').digest('hex')
}

function cleanText(value, max = 1000) {
  if (typeof value !== 'string') return null
  const text = value.trim()
  return text ? text.slice(0, max) : null
}

function regionCodeFromText(value) {
  const text = cleanText(value, 200) || ''
  if (/天津/.test(text)) return 'CN-TJ'
  if (/北京/.test(text)) return 'CN-BJ'
  if (/上海/.test(text)) return 'CN-SH'
  if (/重庆/.test(text)) return 'CN-CQ'
  if (/广东/.test(text)) return 'CN-GD'
  if (/浙江/.test(text)) return 'CN-ZJ'
  if (/江苏/.test(text)) return 'CN-JS'
  if (/山东/.test(text)) return 'CN-SD'
  if (/吉林/.test(text)) return 'CN-JL'
  return text ? `CN-REGION-${sha256Json(text).slice(0, 10)}` : 'CN-UNKNOWN'
}

function sourceUrlFromCard(card) {
  const urls = Array.isArray(card?.evidence_source_urls)
    ? card.evidence_source_urls.filter((value) => typeof value === 'string' && /^https:\/\//i.test(value)).sort()
    : []
  return urls[0] || null
}

function sourceIdFromUrl(value) {
  try {
    return new URL(value).hostname.toLowerCase()
  } catch {
    return 'unknown-public-source'
  }
}

function publicPayloadFromCard(card) {
  const facts = asObject(card?.facts)
  if (!facts || facts.verification_status !== 'VERIFIED') return null
  const evidenceSourceUrls = Array.isArray(card?.evidence_source_urls)
    ? [...new Set(card.evidence_source_urls
        .filter((value) => typeof value === 'string' && /^https:\/\//i.test(value)))]
        .sort()
    : []
  if (evidenceSourceUrls.length === 0) return null
  return {
    opportunity_id: cleanText(card.opportunity_id, 200),
    facts,
    evidence_source_urls: evidenceSourceUrls,
  }
}

function publicObservation(card, observedAt) {
  const payload = publicPayloadFromCard(card)
  if (!payload?.opportunity_id) return null
  const sourceUrl = sourceUrlFromCard(payload)
  if (!sourceUrl) return null
  return {
    opportunity_id: payload.opportunity_id,
    region_code: regionCodeFromText(payload.facts.region),
    source_id: sourceIdFromUrl(sourceUrl),
    source_url: sourceUrl,
    lifecycle_state: cleanText(payload.facts.lifecycle_state, 160),
    fact_hash: sha256Json(payload),
    payload,
    observed_at: observedAt,
  }
}

function changedFields(previousPayload, nextPayload) {
  const previous = asObject(previousPayload) || {}
  const next = asObject(nextPayload) || {}
  const previousFacts = asObject(previous.facts) || {}
  const nextFacts = asObject(next.facts) || {}
  const fields = new Set()
  for (const key of new Set([...Object.keys(previousFacts), ...Object.keys(nextFacts)])) {
    if (stableJson(previousFacts[key]) !== stableJson(nextFacts[key])) fields.add(`facts.${key}`)
  }
  if (stableJson(previous.evidence_source_urls || []) !== stableJson(next.evidence_source_urls || [])) {
    fields.add('evidence_source_urls')
  }
  return [...fields].sort()
}

async function upsertObservationTx(tx, observation, collectorRunId = null) {
  const existingRows = await tx`
    SELECT current_version, current_fact_hash, current_payload, first_seen_at, last_seen_at
    FROM public_opportunities
    WHERE opportunity_id = ${observation.opportunity_id}
    FOR UPDATE
  `
  const existing = existingRows[0] || null
  const observedAt = new Date(observation.observed_at)
  if (Number.isNaN(observedAt.getTime())) throw new Error('PUBLIC_OBSERVATION_TIME_INVALID')

  if (!existing) {
    await tx`
      INSERT INTO public_opportunities (
        opportunity_id, region_code, source_id, source_url,
        current_version, current_fact_hash, current_payload, lifecycle_state,
        first_seen_at, last_seen_at, last_changed_at, updated_at
      ) VALUES (
        ${observation.opportunity_id}, ${observation.region_code}, ${observation.source_id}, ${observation.source_url},
        1, ${observation.fact_hash}, ${tx.json(observation.payload)}, ${observation.lifecycle_state},
        ${observedAt.toISOString()}, ${observedAt.toISOString()}, ${observedAt.toISOString()}, now()
      )
    `
    await tx`
      INSERT INTO public_opportunity_versions (
        opportunity_id, version, fact_hash, payload, changed_fields, observed_at, collector_run_id
      ) VALUES (
        ${observation.opportunity_id}, 1, ${observation.fact_hash}, ${tx.json(observation.payload)},
        ${tx.json(['INITIAL'])}, ${observedAt.toISOString()}, ${collectorRunId}
      )
      ON CONFLICT (opportunity_id, fact_hash) DO NOTHING
    `
    return { created: true, changed: true, stale: false, version: 1 }
  }

  const previousSeen = new Date(existing.last_seen_at).getTime()
  if (Number.isFinite(previousSeen) && observedAt.getTime() < previousSeen) {
    return { created: false, changed: false, stale: true, version: Number(existing.current_version) }
  }

  if (existing.current_fact_hash === observation.fact_hash) {
    await tx`
      UPDATE public_opportunities
      SET region_code = ${observation.region_code},
          source_id = ${observation.source_id},
          source_url = ${observation.source_url},
          lifecycle_state = ${observation.lifecycle_state},
          last_seen_at = GREATEST(last_seen_at, ${observedAt.toISOString()}),
          updated_at = now()
      WHERE opportunity_id = ${observation.opportunity_id}
    `
    return { created: false, changed: false, stale: false, version: Number(existing.current_version) }
  }

  const nextVersion = Number(existing.current_version) + 1
  const fields = changedFields(existing.current_payload, observation.payload)
  await tx`
    UPDATE public_opportunities
    SET region_code = ${observation.region_code},
        source_id = ${observation.source_id},
        source_url = ${observation.source_url},
        current_version = ${nextVersion},
        current_fact_hash = ${observation.fact_hash},
        current_payload = ${tx.json(observation.payload)},
        lifecycle_state = ${observation.lifecycle_state},
        last_seen_at = ${observedAt.toISOString()},
        last_changed_at = ${observedAt.toISOString()},
        updated_at = now()
    WHERE opportunity_id = ${observation.opportunity_id}
  `
  await tx`
    INSERT INTO public_opportunity_versions (
      opportunity_id, version, fact_hash, payload, changed_fields, observed_at, collector_run_id
    ) VALUES (
      ${observation.opportunity_id}, ${nextVersion}, ${observation.fact_hash}, ${tx.json(observation.payload)},
      ${tx.json(fields)}, ${observedAt.toISOString()}, ${collectorRunId}
    )
    ON CONFLICT (opportunity_id, fact_hash) DO NOTHING
  `
  return { created: false, changed: true, stale: false, version: nextVersion, changed_fields: fields }
}

async function publicSchemaVersionCurrent(sql) {
  const relation = await sql`SELECT to_regclass('public_schema_meta')::text AS table_name`
  if (!relation[0]?.table_name) return false
  const rows = await sql`
    SELECT schema_version
    FROM public_schema_meta
    WHERE schema_key = ${PUBLIC_SCHEMA_KEY}
    LIMIT 1
  `
  return rows[0]?.schema_version === PUBLIC_SCHEMA_VERSION
}

export async function ensurePublicIntelligenceSchema() {
  if (schemaPromise) return schemaPromise
  schemaPromise = (async () => {
    const sql = publicIntelligenceDb()
    if (await publicSchemaVersionCurrent(sql)) return

    await sql.begin(async (tx) => {
      await tx`SELECT pg_advisory_xact_lock(hashtext(${PUBLIC_SCHEMA_LOCK_KEY}))`
      if (await publicSchemaVersionCurrent(tx)) return
      for (const statement of PUBLIC_SCHEMA_STATEMENTS) {
        await tx.unsafe(statement)
      }
      await tx`
        INSERT INTO public_schema_meta (schema_key, schema_version, updated_at)
        VALUES (${PUBLIC_SCHEMA_KEY}, ${PUBLIC_SCHEMA_VERSION}, now())
        ON CONFLICT (schema_key) DO UPDATE SET
          schema_version = EXCLUDED.schema_version,
          updated_at = now()
      `
    })
  })().catch((error) => {
    schemaPromise = null
    throw error
  })
  return schemaPromise
}

export function publicAiFactHash(facts, evidenceUrls) {
  return sha256Json({
    facts: asObject(facts) || {},
    evidence_source_urls: Array.isArray(evidenceUrls) ? [...new Set(evidenceUrls)].sort() : [],
  })
}

export async function persistPublicVerifiedSnapshot(snapshot, options = {}) {
  if (!publicIntelligenceDatabaseConfigured()) {
    return { configured: false, persisted: false, snapshot_hash: null }
  }
  const snapshotAsOf = cleanText(snapshot?.snapshot_as_of, 100)
  if (!snapshotAsOf || Number.isNaN(Date.parse(snapshotAsOf))) {
    throw new Error('PUBLIC_SNAPSHOT_AS_OF_INVALID')
  }
  const cards = Array.isArray(snapshot?.opportunity_pool)
    ? snapshot.opportunity_pool
    : Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const snapshotHash = sha256Json(snapshot)

  await ensurePublicIntelligenceSchema()
  const sql = publicIntelligenceDb()
  const result = await sql.begin(async (tx) => {
    // Serialize publication checks across instances so an older concurrent
    // publisher cannot insert after a newer public revision was accepted.
    await tx`SELECT pg_advisory_xact_lock(hashtext('public-verified-snapshot-publish'), 0)`
    await tx`SELECT pg_advisory_xact_lock(hashtext('public-verified-snapshot'), hashtext(${snapshotAsOf}))`
    const latest = await tx`
      SELECT snapshot_as_of, snapshot_hash
      FROM public_verified_snapshots
      ORDER BY snapshot_as_of DESC, materialized_at DESC
      LIMIT 1
    `
    if (options.requireBaseMatch === true) {
      const actualBaseHash = latest[0]?.snapshot_hash ?? null
      const actualBaseAsOf = latest[0]?.snapshot_as_of
        ? new Date(latest[0].snapshot_as_of).toISOString()
        : null
      const expectedBaseAsOf = options.expectedBaseAsOf
        ? new Date(options.expectedBaseAsOf).toISOString()
        : null
      if (actualBaseHash !== (options.expectedBaseHash ?? null) || actualBaseAsOf !== expectedBaseAsOf) {
        throw new Error('PUBLIC_SNAPSHOT_BASE_CHANGED')
      }
    }
    if (latest[0]) {
      const latestMs = Date.parse(latest[0].snapshot_as_of)
      const candidateMs = Date.parse(snapshotAsOf)
      if (candidateMs < latestMs) throw new Error('PUBLIC_SNAPSHOT_ROLLBACK_REJECTED')
      if (candidateMs === latestMs && latest[0].snapshot_hash !== snapshotHash) {
        throw new Error('PUBLIC_SNAPSHOT_REVISION_CONFLICT')
      }
    }
    const existing = await tx`
      SELECT snapshot_hash
      FROM public_verified_snapshots
      WHERE snapshot_as_of = ${snapshotAsOf}
      LIMIT 1
    `
    if (existing[0] && existing[0].snapshot_hash !== snapshotHash) {
      throw new Error('PUBLIC_SNAPSHOT_REVISION_CONFLICT')
    }
    const inserted = await tx`
      INSERT INTO public_verified_snapshots (
        snapshot_hash, snapshot_as_of, payload, opportunity_count
      ) VALUES (
        ${snapshotHash}, ${snapshotAsOf}, ${tx.json(snapshot)}, ${cards.length}
      )
      ON CONFLICT (snapshot_hash) DO NOTHING
      RETURNING snapshot_hash
    `
    return { inserted: inserted.length > 0 }
  })
  return {
    configured: true,
    persisted: true,
    inserted: result.inserted,
    snapshot_hash: snapshotHash,
  }
}

/** Read the latest durable public revision without schema setup or writes. */
export async function latestPublicVerifiedSnapshotForPublish() {
  if (!publicIntelligenceDatabaseConfigured()) return null
  const sql = publicIntelligenceDb()
  try {
    const rows = await sql`
      SELECT snapshot_hash, payload
      FROM public_verified_snapshots
      ORDER BY snapshot_as_of DESC, materialized_at DESC
      LIMIT 1
    `
    return rows[0] || null
  } catch (error) {
    // A fresh database may not have run application schema setup yet. Treat
    // only this missing-table case as an empty durable store; persist performs
    // the normal schema setup after candidate validation. Other read errors
    // must stop publishing before any durable write.
    if (error?.code === '42P01') return null
    throw error
  }
}

export async function latestPublicVerifiedSnapshot() {
  if (!publicIntelligenceDatabaseConfigured()) return null
  try {
    await ensurePublicIntelligenceSchema()
    const sql = publicIntelligenceDb()
    const rows = await sql`
      SELECT payload
      FROM public_verified_snapshots
      ORDER BY snapshot_as_of DESC, materialized_at DESC
      LIMIT 1
    `
    return rows[0]?.payload || null
  } catch (error) {
    console.warn('durable public snapshot read unavailable', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return null
  }
}

/**
 * Revision-aware read of the latest durable snapshot. Returns
 * { snapshot_hash, payload } where payload is null when the latest row still
 * has `knownHash` (the caller's in-memory copy is current), so warm instances
 * avoid re-downloading ~1.5MB of JSONB on every request. Returns null when the
 * database is unavailable or empty.
 */
export async function latestPublicVerifiedSnapshotIfChanged(knownHash = null) {
  if (!publicIntelligenceDatabaseConfigured()) return null
  try {
    await ensurePublicIntelligenceSchema()
    const sql = publicIntelligenceDb()
    const rows = await sql`
      SELECT
        snapshot_hash,
        CASE WHEN snapshot_hash = ${knownHash || ''} THEN NULL ELSE payload END AS payload
      FROM public_verified_snapshots
      ORDER BY snapshot_as_of DESC, materialized_at DESC
      LIMIT 1
    `
    if (!rows[0]) return null
    return { snapshot_hash: rows[0].snapshot_hash, payload: rows[0].payload ?? null }
  } catch (error) {
    console.warn('durable public snapshot revision read unavailable', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    // Keep database failure distinct from an empty/unconfigured database so
    // callers can retain a validated last-good snapshot and report degradation.
    throw error
  }
}

export async function materializeVerifiedSnapshot(snapshot) {
  if (!publicIntelligenceDatabaseConfigured()) return { configured: false, materialized: false, regions: [] }
  const snapshotAsOf = cleanText(snapshot?.snapshot_as_of, 100)
  if (!snapshotAsOf || Number.isNaN(Date.parse(snapshotAsOf))) throw new Error('PUBLIC_SNAPSHOT_AS_OF_INVALID')
  const pool = Array.isArray(snapshot?.opportunity_pool) ? snapshot.opportunity_pool : []
  const cards = pool.length ? pool : Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const observations = cards
    .map((card) => publicObservation(card, snapshotAsOf))
    .filter(Boolean)
  const grouped = new Map()
  for (const observation of observations) {
    const list = grouped.get(observation.region_code) || []
    list.push(observation)
    grouped.set(observation.region_code, list)
  }

  await ensurePublicIntelligenceSchema()
  const sql = publicIntelligenceDb()
  const regions = []
  for (const [regionCode, rows] of grouped) {
    rows.sort((left, right) => left.opportunity_id.localeCompare(right.opportunity_id))
    const snapshotHash = sha256Json({
      region_code: regionCode,
      snapshot_as_of: snapshotAsOf,
      opportunities: rows.map((row) => ({ id: row.opportunity_id, fact_hash: row.fact_hash })),
    })
    const result = await sql.begin(async (tx) => {
      await tx`SELECT pg_advisory_xact_lock(hashtext(${regionCode}), hashtext(${snapshotHash}))`
      const existing = await tx`
        SELECT 1 FROM public_snapshot_materializations
        WHERE region_code = ${regionCode} AND snapshot_hash = ${snapshotHash}
        LIMIT 1
      `
      if (existing.length) return { skipped: true, changed: 0, created: 0 }
      let changed = 0
      let created = 0
      for (const row of rows) {
        const observationResult = await upsertObservationTx(tx, row)
        if (observationResult.changed) changed += 1
        if (observationResult.created) created += 1
      }
      await tx`
        INSERT INTO public_snapshot_materializations (
          region_code, snapshot_hash, snapshot_as_of, opportunity_count
        ) VALUES (
          ${regionCode}, ${snapshotHash}, ${snapshotAsOf}, ${rows.length}
        )
        ON CONFLICT (region_code, snapshot_hash) DO NOTHING
      `
      return { skipped: false, changed, created }
    })
    regions.push({ region_code: regionCode, snapshot_hash: snapshotHash, opportunity_count: rows.length, ...result })
  }
  return { configured: true, materialized: true, regions }
}

export async function getSharedPublicAiBrief({
  opportunityId,
  factHash,
  windowState,
  briefType = 'PUBLIC_ACTION_DECISION',
  promptVersion,
}) {
  if (!publicIntelligenceDatabaseConfigured()) {
    return { result: null, cache_hit: false, durable: false, generated_at: null }
  }
  try {
    await ensurePublicIntelligenceSchema()
    const sql = publicIntelligenceDb()
    const cached = await sql`
      SELECT result, generated_at
      FROM public_ai_briefs
      WHERE opportunity_id = ${opportunityId}
        AND fact_hash = ${factHash}
        AND window_state = ${windowState}
        AND brief_type = ${briefType}
        AND prompt_version = ${promptVersion}
      LIMIT 1
    `
    if (!cached[0]) {
      return { result: null, cache_hit: false, durable: true, generated_at: null }
    }
    return {
      result: cached[0].result,
      cache_hit: true,
      durable: true,
      generated_at: new Date(cached[0].generated_at).toISOString(),
    }
  } catch (error) {
    console.warn('shared public AI cache read unavailable', {
      opportunity_id: opportunityId,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return { result: null, cache_hit: false, durable: false, generated_at: null }
  }
}

async function readSharedPublicAiBrief(sql, { opportunityId, factHash, windowState, briefType, promptVersion }) {
  const cached = await sql`
    SELECT result, generated_at
    FROM public_ai_briefs
    WHERE opportunity_id = ${opportunityId}
      AND fact_hash = ${factHash}
      AND window_state = ${windowState}
      AND brief_type = ${briefType}
      AND prompt_version = ${promptVersion}
    LIMIT 1
  `
  if (!cached[0]) return null
  return {
    result: cached[0].result,
    cache_hit: true,
    durable: true,
    generated_at: new Date(cached[0].generated_at).toISOString(),
  }
}

export async function getOrCreateSharedPublicAiBrief({
  opportunityId,
  factHash,
  windowState,
  briefType = 'PUBLIC_ACTION_DECISION',
  promptVersion,
  createResult,
}) {
  if (typeof createResult !== 'function') throw new Error('PUBLIC_AI_CREATE_RESULT_REQUIRED')
  if (!publicIntelligenceDatabaseConfigured()) {
    return { result: await createResult(), cache_hit: false, durable: false, generated_at: new Date().toISOString() }
  }
  // Never hold a database transaction, pooled connection or advisory lock
  // while the model is generating (that can take tens of seconds and a batch
  // would pin one connection per item). Read the cache, generate outside any
  // transaction, then insert first-writer-wins. Concurrent generators on
  // different instances may both call the model once, but they converge on a
  // single durable answer. Same-instance duplicates are already collapsed by
  // the in-flight map in _analyzeCore.js.
  let createdResult = null
  let sql = null
  const cacheKeyValues = { opportunityId, factHash, windowState, briefType, promptVersion }
  try {
    await ensurePublicIntelligenceSchema()
    sql = publicIntelligenceDb()
    const cached = await readSharedPublicAiBrief(sql, cacheKeyValues)
    if (cached) return cached
  } catch (error) {
    console.warn('shared public AI cache read unavailable; generating without durable cache hit', {
      opportunity_id: opportunityId,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    sql = null
  }

  createdResult = await createResult()
  if (!sql) {
    return { result: createdResult, cache_hit: false, durable: false, generated_at: new Date().toISOString() }
  }

  try {
    const inserted = await sql`
      INSERT INTO public_ai_briefs (
        opportunity_id, fact_hash, window_state, brief_type, prompt_version, result, generated_at
      ) VALUES (
        ${opportunityId}, ${factHash}, ${windowState}, ${briefType}, ${promptVersion},
        ${sql.json(createdResult)}, now()
      )
      ON CONFLICT (opportunity_id, fact_hash, window_state, brief_type, prompt_version)
      DO NOTHING
      RETURNING generated_at
    `
    if (inserted[0]) {
      return {
        result: createdResult,
        cache_hit: false,
        durable: true,
        generated_at: new Date(inserted[0].generated_at).toISOString(),
      }
    }
    // Another instance finished first: serve the stored answer so every user
    // sees the same shared public decision.
    const winner = await readSharedPublicAiBrief(sql, cacheKeyValues)
    if (winner) return { ...winner, cache_hit: false }
    return { result: createdResult, cache_hit: false, durable: false, generated_at: new Date().toISOString() }
  } catch (error) {
    console.warn('shared public AI cache write unavailable; returning request-local result', {
      opportunity_id: opportunityId,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return {
      result: createdResult,
      cache_hit: false,
      durable: false,
      generated_at: new Date().toISOString(),
    }
  }
}
