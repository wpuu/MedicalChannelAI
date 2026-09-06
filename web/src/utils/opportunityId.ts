const SAFE_OPPORTUNITY_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]*$/

/**
 * Opportunity ids are stable opaque identifiers produced by multiple verified
 * source pipelines (for example ccgp_* and verified_*). The UI must not infer
 * a source-specific UUID shape; it only enforces a compact URL/database-safe
 * token contract shared with the private API boundary.
 */
export function isStableOpportunityId(value: unknown): value is string {
  if (typeof value !== 'string') return false
  if (!value || value.length > 200 || value.trim() !== value) return false
  return SAFE_OPPORTUNITY_ID.test(value)
}
