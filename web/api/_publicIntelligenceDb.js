import { privateDatabaseConfigured, privateDb } from './_privateDb.js'

let schemaPromise = null

export function publicIntelligenceDatabaseConfigured() {
  return privateDatabaseConfigured()
}

export function publicIntelligenceDb() {
  return privateDb()
}

export async function ensurePublicIntelligenceSchema() {
  if (schemaPromise) return schemaPromise
  schemaPromise = (async () => {
    const sql = publicIntelligenceDb()
    await sql`
      CREATE TABLE IF NOT EXISTS public_collector_runs (
        id TEXT PRIMARY KEY,
        region_code TEXT NOT NULL,
        source_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at TIMESTAMPTZ,
        summary JSONB NOT NULL DEFAULT '{}'::jsonb
      )
    `
    await sql`
      CREATE INDEX IF NOT EXISTS public_collector_runs_region_started_idx
      ON public_collector_runs (region_code, started_at DESC)
    `
    await sql`
      CREATE TABLE IF NOT EXISTS public_opportunities (
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
      )
    `
    await sql`
      CREATE INDEX IF NOT EXISTS public_opportunities_region_state_idx
      ON public_opportunities (region_code, lifecycle_state, last_changed_at DESC)
    `
    await sql`
      CREATE TABLE IF NOT EXISTS public_opportunity_versions (
        opportunity_id TEXT NOT NULL REFERENCES public_opportunities(opportunity_id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version >= 1),
        fact_hash TEXT NOT NULL CHECK (length(fact_hash) = 64),
        payload JSONB NOT NULL,
        changed_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
        observed_at TIMESTAMPTZ NOT NULL,
        collector_run_id TEXT REFERENCES public_collector_runs(id) ON DELETE SET NULL,
        PRIMARY KEY (opportunity_id, version),
        UNIQUE (opportunity_id, fact_hash)
      )
    `
    await sql`
      CREATE INDEX IF NOT EXISTS public_opportunity_versions_observed_idx
      ON public_opportunity_versions (opportunity_id, observed_at DESC)
    `
    await sql`
      CREATE TABLE IF NOT EXISTS public_ai_briefs (
        opportunity_id TEXT NOT NULL REFERENCES public_opportunities(opportunity_id) ON DELETE CASCADE,
        fact_hash TEXT NOT NULL CHECK (length(fact_hash) = 64),
        window_state TEXT NOT NULL,
        brief_type TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        result JSONB NOT NULL,
        generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (opportunity_id, fact_hash, window_state, brief_type, prompt_version)
      )
    `
    await sql`
      CREATE INDEX IF NOT EXISTS public_ai_briefs_lookup_idx
      ON public_ai_briefs (opportunity_id, fact_hash, generated_at DESC)
    `
  })().catch((error) => {
    schemaPromise = null
    throw error
  })
  return schemaPromise
}
