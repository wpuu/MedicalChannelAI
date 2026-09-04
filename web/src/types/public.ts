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

export interface PublicTodayActionCard {
  rank: number
  opportunity_id: string
  facts: PublicFacts
  evidence_source_urls: string[]
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
  cards: PublicTodayActionCard[]
  opportunity_pool?: PublicTodayActionCard[]
}