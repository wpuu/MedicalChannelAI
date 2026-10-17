export type ModelDecisionStatus =
  | 'NOT_ELIGIBLE'
  | 'BLOCKED_GROUNDING'
  | 'AWAITING_MODEL'
  | 'MODEL_OUTPUT_REJECTED'
  | 'READY'

export type FollowupStatus =
  | 'NEW'
  | 'REVIEWING'
  | 'CONTACTED'
  | 'RELATIONSHIP_VERIFIED'
  | 'PREPARING'
  | 'BID_SUBMITTED'
  | 'WON'
  | 'LOST'
  | 'NOT_FIT'
  | 'MONITOR'
  | 'ARCHIVED'

export type NotFitReason =
  | '没有对应产品'
  | '暂无厂家资源'
  | '医院关系太弱'
  | '项目金额太小'
  | '介入时间太晚'
  | '判断竞争对手已锁定'
  | '科室不匹配'
  | '区域不匹配'
  | '不做租赁项目'
  | '其他'

export type LostReason =
  | '价格/报价竞争失败'
  | '产品或参数不匹配'
  | '厂家/授权资源不足'
  | '医院关系不足'
  | '介入时间太晚'
  | '竞争对手优势明显'
  | '投标/响应执行失败'
  | '客户需求或项目变化'
  | '主动放弃'
  | '其他'

export type WonReason =
  | '产品或参数匹配'
  | '厂家/授权资源有优势'
  | '医院关系或沟通推进有效'
  | '价格或商务条件有优势'
  | '介入时机合适'
  | '投标/响应执行到位'
  | '方案与客户需求匹配'
  | '其他'

export type RelationshipStrength =
  | 'STRONG'
  | 'MEDIUM'
  | 'HISTORICAL'
  | 'WEAK'
  | 'UNKNOWN'
  | 'NONE'

export type CapabilityType =
  | 'DIRECT'
  | 'NEED_MANUFACTURER'
  | 'PARTNER'
  | 'DIRECT_AUTHORIZED'
  | 'DIRECT_UNCONFIRMED'
  | 'RENTAL_CAPABLE'
  | 'CAN_SOURCE_PARTNER'
  | 'SERVICE_ONLY'

export type VerificationStatus = 'VERIFIED' | 'UNVERIFIED' | 'PARTIAL'
export type CoverageStatus = 'FULL' | 'PARTIAL' | 'NONE'
export type PriorityScoreScope = 'PUBLIC' | 'PERSONALIZED'

export interface ProductItem {
  name: string
  category: string | null
  quantity: string | null
  specification: string | null
}

export interface OfficialContact {
  name: string | null
  title: string | null
  phone: string | null
  email: string | null
}

export interface Facts {
  project_code: string | null
  project_name: string | null
  hospital: string | null
  buyer_name?: string | null
  department: string | null
  region: string | null
  market_code?: string | null
  market_name?: string | null
  market_admin_code?: string | null
  lifecycle_stage: string | null
  notice_type?: string | null
  publish_date: string | null
  registration_deadline: string | null
  registration_deadline_date?: string | null
  registration_deadline_precision?: 'MINUTE' | 'DAY' | null
  bid_deadline: string | null
  expected_purchase_date: string | null
  budget: number | null
  procurement_method: string | null
  product_categories?: string[]
  products: ProductItem[] | null
  official_contact: OfficialContact | null
  quality_flags?: string[]
  verification_status: VerificationStatus
  coverage_status: CoverageStatus
}

export interface TargetHospitalInterest {
  hospital: string
  department: string | null
  watched_by_customer: true
  updated_at: string | null
}

export interface HospitalRelationship {
  hospital: string
  department: string | null
  relationship_strength: RelationshipStrength
  owner: string | null
  last_confirmed_at: string | null
}

export interface MatchingProductCapability {
  category: string
  subcategory: string | null
  matched_taxonomy_ids: string[]
  brands: string[]
  capability_type: CapabilityType
}

export interface PartneringPolicy {
  can_find_manufacturer: boolean | null
  can_partner_channel: boolean | null
  can_handle_lease: boolean | null
}

export interface CustomerContext {
  /** Optional only for legacy demo fixtures; real Pilot adapters set it explicitly. */
  target_hospital?: TargetHospitalInterest | null
  hospital_relationship: HospitalRelationship | null
  matching_product_capabilities: MatchingProductCapability[]
  partnering_policy: PartneringPolicy
}

export interface PriorityComponents {
  PRODUCT_EXECUTION_CAPABILITY: number
  RELATIONSHIP: number
  INTERVENTION_STAGE: number
  PROJECT_AMOUNT: number
  /** v2 fields are present for real verified opportunities; legacy demo fixtures may omit them. */
  EXECUTION_FLEXIBILITY?: number
  DEADLINE_URGENCY?: number
  PRODUCT_SPECIFICITY?: number
  PUBLICATION_FRESHNESS?: number
}

export interface Priority {
  score: number
  /** Real v2 adapters must set this explicitly. Missing means legacy fixture/snapshot and is treated as PUBLIC only for backward compatibility. */
  score_scope?: PriorityScoreScope
  components: PriorityComponents
}

export interface Decision {
  action: string
  reasons: string[]
  risks: string[]
  needs_human_confirmation: string[]
}

export interface FollowupRecord {
  id: string
  status: FollowupStatus
  note?: string
  reason?: string
  remind_at?: string
  at: string
  actor: string
}

/**
 * UI view model. The backend wire shape is declared separately in public.ts.
 * Local follow-up state and display timestamps are intentionally UI-only fields.
 */
export interface TodayActionCard {
  rank: number
  opportunity_id: string
  facts: Facts
  evidence_source_urls: string[]
  customer_context: CustomerContext
  priority: Priority
  match_status: string
  recommendation_mode: string
  model_decision_status: ModelDecisionStatus
  model_block_reason: string | null
  decision: Decision | null
  followup_status: FollowupStatus
  followup_history: FollowupRecord[]
  remind_at: string | null
  /** UI-only snapshot provenance retained when a card is opened in Detail. */
  snapshot_meta?: SnapshotMeta
}

/** UI-only source and degradation state for the snapshot that produced a view. */
export interface SnapshotMeta {
  snapshot_as_of: string | null
  source: string
  runtime_origin?: 'PUBLISHED' | 'BUNDLED' | null
  degraded: boolean
  reason: string | null
  collection_coverage?: {
    complete: boolean | null
    last_complete_as_of: string | null
    updated_source_ids: string[]
    failed_source_ids: string[]
  } | null
}

/**
 * Transitional UI-only marker type. Real Public View never returns model requests,
 * and Demo data should not embed them either. Kept optional only while the adapter
 * is being simplified away from the older UI shape.
 */
export interface ModelRequest {
  opportunity_id: string
  status: ModelDecisionStatus
  requested_at: string
}

export interface RecommendationFeedbackSummary {
  responded: number
  effective_surprises: number
  effective_surprise_rate: number | null
}

export interface ProcurementIntentFollowupSummary {
  intent_count: number
  intents_with_formal_successor: number
  candidate_pair_count: number
  /** Authenticated Today display hint; does not alter the public successor counts above. */
  formal_candidates_needing_action?: number
}

/** UI response after Mock or Public View adapter enrichment. */
export interface TodayActionsResponse {
  schema_version: '0.1'
  mode: 'TODAY_ACTIONS'
  input_candidate_count: number
  matched_count: number
  card_count: number
  opportunity_pool_count?: number
  model_request_count: number
  coverage_warning: string
  generated_at: string
  refreshed_at: string
  snapshot_meta?: SnapshotMeta
  today_limit?: number
  today_limit_options?: number[]
  recommendation_feedback_summary?: RecommendationFeedbackSummary
  procurement_intent_followup_summary?: ProcurementIntentFollowupSummary
  cards: TodayActionCard[]
  opportunity_pool?: TodayActionCard[]
  model_requests?: ModelRequest[]
}

export interface FollowupInput {
  status: FollowupStatus
  note?: string
  reason?: string
  remind_at?: string
}

export interface OutreachDraft {
  opportunity_id: string
  generated_at: string
  draft: string
  disclaimer: string
}

export type PriorityTier = 'critical' | 'high' | 'medium' | 'low'
