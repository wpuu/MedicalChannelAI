export const AWARD_EVIDENCE_VERSION: 'EXPLICIT_CNY_SCOPE_V1'
export const LEGACY_AWARD_SCOPE_ERROR: 'AWARD_EVIDENCE_LEGACY_RETIRED_POOL'
export function assertAwardEvidenceCompatibility(snapshot: unknown): void
export function normalizeEvidenceLegalWindows<T>(windows: T[] | null | undefined): T[] | null
export function normalizeAwardLedger<T>(entries: T[] | null | undefined): T[]
export function normalizeAwardPriceReference<T>(reference: T): T | null
export function normalizeAwardEvidenceSnapshot<T>(snapshot: T): T
