import {
  ensurePublicIntelligenceSchema,
  publicIntelligenceDb,
} from './_publicIntelligenceDb.js'

const MAX_HISTORY_VERSIONS = 20
const ALLOWED_CHANGE_FIELDS = new Set([
  'facts.project_number',
  'facts.project_name',
  'facts.buyer_name',
  'facts.hospital_name',
  'facts.department',
  'facts.region',
  'facts.lifecycle_state',
  'facts.notice_type',
  'facts.published_at',
  'facts.registration_deadline',
  'facts.registration_deadline_date',
  'facts.registration_deadline_precision',
  'facts.bid_deadline',
  'facts.expected_procurement_at',
  'facts.expected_procurement_precision',
  'facts.budget',
  'facts.procurement_method',
  'facts.product_categories',
  'facts.product_items',
  'facts.public_contact',
  'facts.verification_status',
  'facts.coverage_status',
  'facts.quality_flags',
  'evidence_source_urls',
])

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function safeValue(value, depth = 0) {
  if (value === null || value === undefined) return null
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') return value.slice(0, 2000)
  if (depth >= 3) return null
  if (Array.isArray(value)) return value.slice(0, 30).map((item) => safeValue(item, depth + 1))
  const record = asObject(value)
  if (!record) return null
  const result = {}
  for (const [key, child] of Object.entries(record).slice(0, 30)) {
    result[key] = safeValue(child, depth + 1)
  }
  return result
}

function pathValue(payload, path) {
  if (path === 'evidence_source_urls') return safeValue(payload?.evidence_source_urls)
  if (!path.startsWith('facts.')) return null
  const facts = asObject(payload?.facts)
  return facts ? safeValue(facts[path.slice('facts.'.length)]) : null
}

function changedFields(row) {
  if (!Array.isArray(row?.changed_fields)) return []
  return row.changed_fields
    .filter((value) => typeof value === 'string' && ALLOWED_CHANGE_FIELDS.has(value))
    .slice(0, 30)
}

function publicSummary(payload) {
  const facts = asObject(payload?.facts) || {}
  return {
    project_name: safeValue(facts.project_name),
    lifecycle_state: safeValue(facts.lifecycle_state),
    registration_deadline: safeValue(facts.registration_deadline),
    registration_deadline_date: safeValue(facts.registration_deadline_date),
    bid_deadline: safeValue(facts.bid_deadline),
    budget: safeValue(facts.budget),
  }
}

export async function publicOpportunityHistory(opportunityId, limit = MAX_HISTORY_VERSIONS) {
  const id = typeof opportunityId === 'string' ? opportunityId.trim() : ''
  const boundedLimit = Number.isInteger(limit) ? Math.max(1, Math.min(MAX_HISTORY_VERSIONS, limit)) : MAX_HISTORY_VERSIONS
  if (!id || id.length > 200) throw new Error('PUBLIC_HISTORY_OPPORTUNITY_ID_INVALID')

  await ensurePublicIntelligenceSchema()
  const sql = publicIntelligenceDb()
  const rows = await sql`
    SELECT version, payload, changed_fields, observed_at
    FROM public_opportunity_versions
    WHERE opportunity_id = ${id}
    ORDER BY version DESC
    LIMIT ${boundedLimit + 1}
  `
  if (rows.length === 0) {
    return {
      schema_version: '0.1',
      mode: 'PUBLIC_OPPORTUNITY_HISTORY',
      opportunity_id: id,
      current_version: null,
      count: 0,
      has_more: false,
      versions: [],
    }
  }

  const descending = [...rows]
  const hasMore = descending.length > boundedLimit
  const windowRows = descending.slice(0, boundedLimit + 1).reverse()
  const visibleStart = hasMore ? 1 : 0
  const versions = []

  for (let index = visibleStart; index < windowRows.length; index += 1) {
    const row = windowRows[index]
    const previous = index > 0 ? windowRows[index - 1] : null
    const fields = Number(row.version) === 1
      ? ['INITIAL']
      : changedFields(row)
    const changes = fields === ['INITIAL']
      ? []
      : fields.map((field) => ({
          field,
          before: previous ? pathValue(previous.payload, field) : null,
          after: pathValue(row.payload, field),
        }))
    versions.push({
      version: Number(row.version),
      observed_at: new Date(row.observed_at).toISOString(),
      change_type: Number(row.version) === 1 ? 'INITIAL' : 'UPDATED',
      changed_fields: fields,
      changes,
      summary: publicSummary(row.payload),
    })
  }

  const currentVersion = Math.max(...descending.map((row) => Number(row.version)))
  return {
    schema_version: '0.1',
    mode: 'PUBLIC_OPPORTUNITY_HISTORY',
    opportunity_id: id,
    current_version: currentVersion,
    count: versions.length,
    has_more: hasMore,
    versions: versions.reverse(),
  }
}
