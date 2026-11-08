/**
 * A04 offline synthetic contract. These are NOT fields of PublicFacts or
 * the existing private profile / database schema. No upload or storage.
 */
export type QualificationEvidenceStatus = 'SATISFIED' | 'NOT_SATISFIED' | 'UNKNOWN'

export interface QualificationOfficialRequirement {
  id: string
  hard: boolean
  source_url: string
  source_locator: string
  source_excerpt: string
  verified: boolean
  evidence_kind?: string
  subject_key?: string
  product_key?: string
}

export interface QualificationOfficialContext {
  project_id: string
  package_id: string
  notice_version: string
  current_notice_version: string
  source_url: string
  verified_at: string
  source_verified: boolean
  requirements_complete: boolean
  attachments_complete: boolean
  version_current_verified: boolean
  requirements: QualificationOfficialRequirement[]
}

export interface QualificationPrivateProof {
  requirement_id: string
  project_id: string
  package_id: string
  notice_version: string
  organization_id: string
  user_id: string
  evidence_kind: string
  subject_key: string
  product_key: string
  consent_to_precheck: boolean
  verified_by_human: boolean
  checked_at: string
  finding: 'MATCH' | 'NOT_MET' | 'UNVERIFIED'
  valid_from?: string
  valid_until?: string
  no_valid_alternative_verified?: boolean
  confirmed_current?: boolean
  conflict_unresolved?: boolean
  /** Never returned by the pure function or rendered in public UI. */
  secret_document_number?: string
}

export interface QualificationCustomerContext {
  organization_id: string
  user_id: string
  consent_to_precheck: boolean
  proofs: QualificationPrivateProof[]
}

export interface QualificationAssessmentInput {
  project_id: string
  package_id: string
  notice_version: string
  organization_id: string
  user_id: string
  as_of: string
  official: QualificationOfficialContext
  customer: QualificationCustomerContext
}

export interface QualificationAssessmentResult {
  status: QualificationEvidenceStatus
  label: string
  missing: string[]
  risks: string[]
  items: Array<{
    index: number
    status: QualificationEvidenceStatus
    reason: string
  }>
  final_qualification_confirmed: false
}

/** Current real cards MUST call this without unverified eligibility data. */
export function evaluateQualificationEvidence(
  input?: QualificationAssessmentInput | null,
): QualificationAssessmentResult
