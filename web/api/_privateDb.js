import postgres from 'postgres'

let sqlClient = null
let schemaPromise = null

function databaseUrl() {
  return String(process.env.DATABASE_URL || process.env.POSTGRES_URL || '').trim()
}

export function privateDatabaseConfigured() {
  return Boolean(databaseUrl())
}

export function privateDb() {
  const url = databaseUrl()
  if (!url) throw new Error('PRIVATE_DATABASE_NOT_CONFIGURED')
  if (!sqlClient) {
    const disableSsl = String(process.env.DATABASE_SSL || '').trim().toLowerCase() === 'disable'
    sqlClient = postgres(url, {
      max: 1,
      idle_timeout: 20,
      connect_timeout: 10,
      prepare: false,
      ssl: disableSsl ? false : 'require',
    })
  }
  return sqlClient
}

const SCHEMA_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS private_organizations (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
  )`,
  `CREATE TABLE IF NOT EXISTS private_users (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES private_organizations(id) ON DELETE CASCADE,
    username_normalized text NOT NULL UNIQUE,
    username_display text NOT NULL,
    password_salt text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'OWNER',
    status text NOT NULL DEFAULT 'ACTIVE',
    display_name text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (role IN ('OWNER', 'ADMIN', 'MEMBER')),
    CHECK (status IN ('ACTIVE', 'DISABLED'))
  )`,
  `CREATE TABLE IF NOT EXISTS private_pilot_invites (
    code_hash text PRIMARY KEY,
    organization_id uuid NULL REFERENCES private_organizations(id) ON DELETE SET NULL,
    expires_at timestamptz NULL,
    used_by uuid NULL REFERENCES private_users(id) ON DELETE SET NULL,
    used_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now()
  )`,
  `CREATE TABLE IF NOT EXISTS private_sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES private_users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
  )`,
  `CREATE INDEX IF NOT EXISTS private_sessions_user_idx ON private_sessions(user_id)`,
  `CREATE INDEX IF NOT EXISTS private_sessions_expiry_idx ON private_sessions(expires_at)`,
  `CREATE TABLE IF NOT EXISTS private_product_capabilities (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES private_organizations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES private_users(id) ON DELETE CASCADE,
    keyword text NOT NULL,
    capability_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
  )`,
  `CREATE INDEX IF NOT EXISTS private_product_capabilities_scope_idx ON private_product_capabilities(organization_id, user_id)`,
  `CREATE TABLE IF NOT EXISTS private_hospital_relationships (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES private_organizations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES private_users(id) ON DELETE CASCADE,
    hospital text NOT NULL,
    department text NULL,
    relationship_strength text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
  )`,
  `CREATE INDEX IF NOT EXISTS private_hospital_relationships_scope_idx ON private_hospital_relationships(organization_id, user_id)`,
  `CREATE TABLE IF NOT EXISTS private_user_preferences (
    user_id uuid PRIMARY KEY REFERENCES private_users(id) ON DELETE CASCADE,
    can_find_manufacturer boolean NULL,
    can_partner_channel boolean NULL,
    can_handle_lease boolean NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
  )`,
  `CREATE TABLE IF NOT EXISTS private_followups (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES private_organizations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES private_users(id) ON DELETE CASCADE,
    opportunity_id text NOT NULL,
    status text NOT NULL,
    remind_at timestamptz NULL,
    public_snapshot jsonb NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, opportunity_id)
  )`,
  `CREATE INDEX IF NOT EXISTS private_followups_scope_idx ON private_followups(organization_id, user_id, updated_at DESC)`,
  `CREATE TABLE IF NOT EXISTS private_followup_events (
    id uuid PRIMARY KEY,
    followup_id uuid NOT NULL REFERENCES private_followups(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES private_users(id) ON DELETE CASCADE,
    mutation_id text NULL,
    status text NOT NULL,
    note text NULL,
    reason text NULL,
    remind_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now()
  )`,
  `ALTER TABLE private_followup_events ADD COLUMN IF NOT EXISTS mutation_id text NULL`,
  `CREATE INDEX IF NOT EXISTS private_followup_events_idx ON private_followup_events(followup_id, created_at DESC)`,
  `CREATE UNIQUE INDEX IF NOT EXISTS private_followup_events_mutation_idx
    ON private_followup_events(user_id, mutation_id)
    WHERE mutation_id IS NOT NULL`,
  `CREATE TABLE IF NOT EXISTS private_recommendation_feedback (
    user_id uuid NOT NULL REFERENCES private_users(id) ON DELETE CASCADE,
    opportunity_id text NOT NULL,
    value text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id, opportunity_id),
    CHECK (value IN ('ALREADY_KNOWN', 'NEW_NOT_VALUABLE', 'NEW_WORTH_FOLLOWING'))
  )`,
]

export async function ensurePrivateSchema() {
  if (schemaPromise) return schemaPromise
  schemaPromise = (async () => {
    const sql = privateDb()
    for (const statement of SCHEMA_STATEMENTS) {
      await sql.unsafe(statement)
    }
  })().catch((error) => {
    schemaPromise = null
    throw error
  })
  return schemaPromise
}
