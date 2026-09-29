export type PublicModelDecisionStatus =
  | 'NOT_ELIGIBLE'
  | 'BLOCKED_GROUNDING'
  | 'AWAITING_MODEL'
  | 'MODEL_OUTPUT_REJECTED'
  | 'READY'

export type PublicMatchStatus = 'MATCHED_PERSONALIZED' | 'MATCHED_CANDIDATE'

export interface PublicFacts {
  project_number: string | null
  project_name: string | null
  buyer_name: string | null
  hospital_name: string | null
  department: string | null
  region: string | null
  market_code?: string | null
  market_name?: string | null
  market_admin_code?: string | null
  lifecycle_state: string | null
  notice_type: string | null
  published_at: string | null
  published_at_precision: string | null
  registration_deadline: string | null
  registration_deadline_date: string | null
  registration_deadline_precision: 'MINUTE' | 'DAY' | null
  bid_deadline: string | null
  expected_procurement_at: string | null
  expected_procurement_precision: string | null
  budget: unknown
  procurement_method: string | null
  product_categories: string[]
  product_items: unknown[]
  public_contact: unknown
  quality_flags?: string[]
  verification_status: string | null
  coverage_status: string | null
}

export interface PublicTargetHospital {
  hospital_name: string
  department: string | null
  watched_by_customer: true
  updated_at: string | null
}

export interface PublicHospitalRelationship {
  hospital_name: string
  department: string | null
  relationship_strength: string | null
  owner: string | null
  confirmed_by_customer: boolean
  last_confirmed_at: string | null
}

export interface PublicProductCapability {
  category: string | null
  subcategory: string | null
  matched_taxonomy_ids: string[]
  brands: string[]
  capability_type: string | null
}

export interface PublicPartneringPolicy {
  can_seek_temporary_manufacturer: boolean | null
  can_cooperate_with_channel_partner: boolean | null
  can_do_rental_projects: boolean | null
}

export interface PublicCustomerContext {
  context_type: 'CUSTOMER_PRIVATE_FACTS'
  business_role: string | null
  target_hospital: PublicTargetHospital | null
  hospital_relationship: PublicHospitalRelationship | null
  matching_product_capabilities: PublicProductCapability[]
  partnering_policy: PublicPartneringPolicy
}

export interface PublicPriorityComponent {
  code: string
  points: number
  max_points: number
  basis: string
  profile_paths: string[]
  opportunity_paths: string[]
}

export interface PublicPriority {
  schema_version: string
  score: number
  score_type: string
  /** PUBLIC = official/open facts only; PERSONALIZED = authenticated private profile was applied. */
  score_scope?: 'PUBLIC' | 'PERSONALIZED'
  components: PublicPriorityComponent[]
  warnings: string[]
  interpretation: 'BUSINESS_PRIORITY_NOT_WIN_PROBABILITY'
}

export interface PublicDecision {
  action: string
  reasons: string[]
  risks: string[]
  supporting_fact_ids: string[]
  supporting_profile_paths: string[]
  requires_human_confirmation: boolean
}

/**
 * Statutory challenge window (质疑期) derived from public facts under
 * 财政部令第94号. An estimate, deliberately kept outside `facts`; see
 * pipeline/medical_channel_pipeline/legal_windows.py for the rules.
 */
export interface PublicLegalWindow {
  code: 'DOCUMENT_CHALLENGE' | 'RESULT_CHALLENGE'
  anchor_kind: string
  anchor_date: string
  /** Present only when the statutory clock starts after the anchor (e.g. 中标公告期限). */
  clock_start_date?: string
  deadline_date: string
  remaining_working_days: number
  status: 'OPEN' | 'CLOSED'
  /** Present only when the dates fall outside the official holiday calendar coverage. */
  calendar?: string
}

/** Working-day calendar embedded in the snapshot (国务院办公厅节假日安排). */
export interface PublicWorkingCalendar {
  schema_version: string
  code: string
  coverage_from: string
  coverage_to: string
  holidays: string[]
  adjusted_workdays: string[]
  legal_basis?: string
  challenge_working_days?: number
  challenge_reply_working_days?: number
  complaint_working_days?: number
  award_notice_period_working_days?: number
}

export interface PublicTodayActionCard {
  rank: number
  opportunity_id: string
  facts: PublicFacts
  evidence_source_urls: string[]
  legal_windows?: PublicLegalWindow[] | null
  customer_context: PublicCustomerContext
  priority: PublicPriority
  match_status: PublicMatchStatus
  recommendation_mode: string
  model_decision_status: PublicModelDecisionStatus
  model_block_reason: string | null
  decision: PublicDecision | null
  /** Authenticated Pilot Today endpoint may inline the user's current follow-up summary. */
  followup_status?: string | null
  remind_at?: string | null
}

export interface PublicRecommendationFeedbackSummary {
  responded: number
  effective_surprises: number
  effective_surprise_rate: number | null
}

export interface PublicProcurementIntentFollowupSummary {
  intent_count: number
  intents_with_formal_successor: number
  candidate_pair_count: number
  /** Authenticated Today only: unique formal candidates not yet explicitly handled by this account. */
  formal_candidates_needing_action?: number
}

export type PublicAwardPackageStatus = 'AWARDED' | 'FAILED'
export type PublicAwardStatus = 'AWARDED' | 'PARTIALLY_FAILED' | 'ALL_PACKAGES_FAILED'

export interface PublicAwardLedgerPackage {
  package_no: string | null
  status: PublicAwardPackageStatus
  supplier_name: string | null
  amount_cny: number | null
  failure_reason: string | null
}

export interface PublicAwardLedgerItem {
  package_no: string | null
  /** Catalogue category when the notice states one (黑龙江 品目名称, 河北 货物类/服务类). */
  category?: string | null
  name: string | null
  brand: string | null
  model: string | null
  quantity: string | null
  unit_price_cny: number | null
}

/** One coarse device family of the shipped taxonomy (ordered; first match wins). */
export interface PublicDeviceFamily {
  code: string
  label: string
  /** Normalised (upper-case, half-width) substrings. */
  keywords: string[]
  /** Whole Latin/digit tokens such as CT, DR, MRI. */
  acronyms: string[]
}

/**
 * One 标的 line of a published 中标/成交 notice with a single brand and a
 * parseable unit price. Pure evidence: no averages, no market price.
 */
export interface PublicAwardPriceReferenceRow {
  award_id: string
  market_code: string
  published_at: string | null
  buyer_name: string | null
  project_number: string | null
  family: string | null
  name: string
  brand: string
  model: string | null
  quantity: string | null
  unit_price_cny: number
  /** Identical lines folded into this row (e.g. three 品目号 rows for three units). */
  line_count: number
  source_url: string
}

export interface PublicAwardPriceReference {
  schema_version: string
  lookback_days: number
  max_rows: number
  row_count: number
  truncated: boolean
  family_row_counts: Record<string, number>
  families: PublicDeviceFamily[]
  rows: PublicAwardPriceReferenceRow[]
}

/**
 * Compact projection of one official 中标/成交 result notice. Awards are a
 * separate record type: they retire the matching project from the pool and
 * expose supplier / brand / model / price evidence with the statutory
 * RESULT_CHALLENGE window. Every number is verifiable at `source_url`.
 */
export interface PublicAwardLedgerEntry {
  award_id: string
  project_number: string
  project_name: string | null
  buyer_name: string | null
  region: string | null
  notice_type: string | null
  result_kind: 'AWARD' | 'DEAL'
  lifecycle_state: 'AWARDED'
  published_at: string | null
  procurement_method: string | null
  total_amount_cny: number | null
  amount_basis: 'SUMMARY_TOTAL' | 'PACKAGE_SUM' | null
  award_status: PublicAwardStatus | null
  package_count: number
  item_count: number
  packages: PublicAwardLedgerPackage[]
  items: PublicAwardLedgerItem[]
  source_url: string
  legal_windows: PublicLegalWindow[] | null
  market_code?: string
}

/**
 * Exact H5-safe response returned by the verified boundary. The authenticated
 * Pilot endpoint may choose the account's configured number of Today cards;
 * `opportunity_pool` retains the full currently actionable pool.
 */
export interface TodayActionsPublicResponse {
  schema_version: '0.1'
  mode: 'TODAY_ACTIONS'
  snapshot_as_of: string
  input_candidate_count: number
  matched_count: number
  card_count: number
  opportunity_pool_count?: number
  model_request_count: number
  coverage_warning: 'PARTIAL_OR_SOURCE_SPECIFIC_COVERAGE_MAY_APPLY'
  today_limit?: number
  today_limit_options?: number[]
  recommendation_feedback_summary?: PublicRecommendationFeedbackSummary
  procurement_intent_followup_summary?: PublicProcurementIntentFollowupSummary
  working_calendar?: PublicWorkingCalendar | null
  /** Pool records retired because an official 中标/成交 result is published. */
  awarded_project_count?: number
  /** Newest-first, bounded ledger of published awards (may be empty). */
  award_ledger?: PublicAwardLedgerEntry[]
  /** 成交价参考: brand × model × unit price lines from published awards. */
  award_price_reference?: PublicAwardPriceReference | null
  cards: PublicTodayActionCard[]
  opportunity_pool?: PublicTodayActionCard[]
}
