import { authenticatedUser, sendJson } from './_auth.js'
import { privateDatabaseConfigured, privateDb } from './_privateDb.js'

const FOLLOWUP_STATUSES = new Set([
  'NEW', 'REVIEWING', 'CONTACTED', 'RELATIONSHIP_VERIFIED', 'PREPARING',
  'BID_SUBMITTED', 'WON', 'LOST', 'NOT_FIT', 'MONITOR', 'ARCHIVED',
])

function nullableText(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function nullableNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function sanitizeStoredSnapshot(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const rawFacts = value.facts
  if (!rawFacts || typeof rawFacts !== 'object' || Array.isArray(rawFacts)) return null
  const facts = {
    project_number: nullableText(rawFacts.project_number),
    project_name: nullableText(rawFacts.project_name),
    buyer_name: nullableText(rawFacts.buyer_name),
    hospital_name: nullableText(rawFacts.hospital_name),
    department: nullableText(rawFacts.department),
    lifecycle_state: nullableText(rawFacts.lifecycle_state),
    published_at: nullableText(rawFacts.published_at),
    bid_deadline: nullableText(rawFacts.bid_deadline),
    expected_procurement_at: nullableText(rawFacts.expected_procurement_at),
    budget_cny: nullableNumber(rawFacts.budget_cny),
  }
  const evidenceSourceUrls = Array.isArray(value.evidence_source_urls)
    ? value.evidence_source_urls
        .filter((item) => typeof item === 'string' && /^https:\/\//i.test(item))
        .slice(0, 50)
    : []
  return { facts, evidence_source_urls: evidenceSourceUrls }
}

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }

  try {
    const user = await authenticatedUser(request)
    if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    const sql = privateDb()
    const rows = await sql`
      SELECT
        f.opportunity_id,
        f.status,
        f.remind_at,
        f.public_snapshot,
        f.updated_at,
        (
          SELECT e.note
          FROM private_followup_events e
          WHERE e.followup_id = f.id
            AND e.user_id = ${user.id}
            AND e.note IS NOT NULL
            AND length(trim(e.note)) > 0
          ORDER BY e.created_at DESC, e.id DESC
          LIMIT 1
        ) AS latest_note
      FROM private_followups f
      WHERE f.user_id = ${user.id}
        AND f.organization_id = ${user.organization_id}
      ORDER BY f.updated_at DESC, f.id DESC
      LIMIT 100
    `

    const items = []
    for (const row of rows) {
      if (!FOLLOWUP_STATUSES.has(row.status)) continue
      const snapshot = sanitizeStoredSnapshot(row.public_snapshot)
      if (!snapshot) continue
      items.push({
        opportunity_id: row.opportunity_id,
        followup_status: row.status,
        remind_at: row.remind_at ? new Date(row.remind_at).toISOString() : null,
        latest_note: nullableText(row.latest_note),
        followup_updated_at: new Date(row.updated_at).toISOString(),
        facts: snapshot.facts,
        evidence_source_urls: snapshot.evidence_source_urls,
      })
    }

    return sendJson(response, 200, {
      schema_version: '0.1',
      mode: 'FOLLOWED_OPPORTUNITIES',
      count: items.length,
      items,
    })
  } catch (error) {
    console.error('private followed list failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'FOLLOWED_REQUEST_FAILED' })
  }
}
