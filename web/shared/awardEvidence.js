// Read-time projection only. Canonical records and stored snapshots stay intact.
// Bump this contract when the producer's money/scope checks change; timestamps,
// hashes and the old EXPLICIT_UNIT label alone do not prove those checks ran.
export const AWARD_EVIDENCE_VERSION = 'EXPLICIT_CNY_SCOPE_V1'
export const LEGACY_AWARD_SCOPE_ERROR = 'AWARD_EVIDENCE_LEGACY_RETIRED_POOL'

export function assertAwardEvidenceCompatibility(snapshot) {
  if (Number(snapshot?.awarded_project_count) > 0 && snapshot?.award_projection_version !== AWARD_EVIDENCE_VERSION) {
    // A derived pool already lost projects. Masking its count cannot restore them.
    throw new Error(LEGACY_AWARD_SCOPE_ERROR)
  }
}

function knownAmount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null
}

export function normalizeEvidenceLegalWindows(windows) {
  if (!Array.isArray(windows)) return null
  return windows.filter(item => item && typeof item === 'object').map(item => ({
    ...item,
    anchor_kind: 'UNVERIFIED',
    anchor_date: null,
    clock_start_date: null,
    deadline_date: null,
    remaining_working_days: 0,
    status: 'UNKNOWN',
    uncertainty_reason: 'APPLICABILITY_ANCHOR_AND_LEGAL_SOURCE_UNVERIFIED',
  }))
}

export function normalizeAwardLedger(entries) {
  if (!Array.isArray(entries)) return []
  return entries.map(entry => {
    const current = entry.projection_version === AWARD_EVIDENCE_VERSION
    return {
      ...entry,
      total_amount_cny: current && ['VERIFIED_SUMMARY_TOTAL', 'VERIFIED_PACKAGE_SUM'].includes(entry.total_amount_basis)
        ? knownAmount(entry.total_amount_cny) : null,
      legal_windows: normalizeEvidenceLegalWindows(entry.legal_windows),
      packages: (entry.packages ?? []).map(pkg => ({
        ...pkg,
        amount_cny: current && pkg.amount_basis === 'EXPLICIT_CNY' ? knownAmount(pkg.amount_cny) : null,
      })),
      items: (entry.items ?? []).map(item => ({
        ...item,
        unit_price_cny: current && item.unit_price_basis === 'EXPLICIT_UNIT' ? knownAmount(item.unit_price_cny) : null,
      })),
    }
  })
}

export function normalizeAwardPriceReference(reference) {
  if (!reference || !Array.isArray(reference.rows) || !Array.isArray(reference.families)) return null
  const rows = reference.rows.filter(row => row.projection_version === AWARD_EVIDENCE_VERSION &&
    row.unit_price_basis === 'EXPLICIT_UNIT' && knownAmount(row.unit_price_cny) > 0)
  const family_row_counts = {}
  for (const row of rows) {
    const family = row.family ?? 'OTHER'
    family_row_counts[family] = (family_row_counts[family] ?? 0) + 1
  }
  return { ...reference, rows: rows.map(row => ({ ...row })), row_count: rows.length, family_row_counts }
}

export function normalizeAwardEvidenceSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return snapshot
  assertAwardEvidenceCompatibility(snapshot)
  const result = { ...snapshot }
  if ('legal_windows' in result) result.legal_windows = normalizeEvidenceLegalWindows(result.legal_windows)
  for (const key of ['cards', 'opportunity_pool']) {
    if (Array.isArray(result[key])) result[key] = result[key].map(normalizeAwardEvidenceSnapshot)
  }
  if ('award_ledger' in result) result.award_ledger = normalizeAwardLedger(result.award_ledger)
  if ('award_price_reference' in result) result.award_price_reference = normalizeAwardPriceReference(result.award_price_reference)
  return result
}
