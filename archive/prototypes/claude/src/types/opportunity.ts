// ============================================================
// 医疗商机助手 - 核心数据类型定义
// ============================================================

/** AI 行动建议的生成状态 */
export type ModelDecisionStatus =
  | 'NOT_ELIGIBLE'
  | 'BLOCKED_GROUNDING'
  | 'AWAITING_MODEL'
  | 'MODEL_OUTPUT_REJECTED'
  | 'READY';

/** 官方事实的核验状态 */
export type VerificationStatus = 'VERIFIED' | 'UNVERIFIED' | 'PARTIAL';

/** 当前区域/项目类型的数据覆盖状态 */
export type CoverageStatus = 'FULL' | 'PARTIAL' | 'LIMITED';

/** 项目生命周期阶段 */
export type LifecycleStage =
  | 'DEMAND_SIGNAL' // 需求预告/意向
  | 'REGISTRATION' // 报名中
  | 'BIDDING' // 招标/评标中
  | 'AWARDED' // 已中标/结果公示
  | 'CONTRACT_EXECUTION' // 合同/执行阶段
  | 'MAINTENANCE_RENEWAL'; // 维保/续约

export type RelationshipStrength = 'STRONG' | 'MEDIUM' | 'WEAK' | 'NONE';

export type CapabilityType = 'DIRECT' | 'NEEDS_SOURCING' | 'PARTIAL_MATCH';

export type PriorityTier = 'IMMEDIATE' | 'FOCUS' | 'MONITOR' | 'NORMAL';

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
  | 'ARCHIVED';

export type NotFitReason =
  | 'NO_MATCHING_PRODUCT'
  | 'NO_VENDOR_RESOURCE'
  | 'WEAK_HOSPITAL_RELATIONSHIP'
  | 'BUDGET_TOO_SMALL'
  | 'TOO_LATE_TO_INTERVENE'
  | 'COMPETITOR_LOCKED_IN'
  | 'DEPARTMENT_MISMATCH'
  | 'REGION_MISMATCH'
  | 'NO_LEASING_SUPPORT'
  | 'OTHER';

// ---------------- 官方事实 ----------------

export interface ProductItem {
  name: string;
  spec?: string | null;
  quantity?: number | null;
}

export interface OfficialContact {
  name?: string | null;
  phone?: string | null;
  org?: string | null;
}

export interface OfficialFacts {
  project_code: string | null;
  project_name: string | null;
  hospital_name: string | null;
  department: string | null;
  region: string | null;
  lifecycle_stage: LifecycleStage | null;
  publish_date: string | null;
  registration_deadline: string | null;
  bid_deadline: string | null;
  estimated_procurement_date: string | null;
  budget_amount: number | null;
  procurement_method: string | null;
  products: ProductItem[];
  official_contact: OfficialContact | null;
  verification_status: VerificationStatus;
  coverage_status: CoverageStatus;
}

export interface EvidenceLink {
  label: string;
  url: string;
}

// ---------------- 客户自己的资源 ----------------

export interface HospitalRelationship {
  hospital_name: string;
  department: string | null;
  relationship_strength: RelationshipStrength;
  owner: string | null;
  last_confirmed_at: string | null;
}

export interface ProductCapability {
  category: string;
  subcategory?: string | null;
  matched_taxonomy_ids?: string[];
  brands?: string[];
  capability_type: CapabilityType;
}

export interface PartneringPolicy {
  can_source_new_vendor: boolean;
  can_partner_with_other_distributor: boolean;
  can_support_leasing: boolean;
}

export interface CustomerContext {
  hospital_relationship: HospitalRelationship | null;
  matching_product_capabilities: ProductCapability[];
  partnering_policy: PartneringPolicy | null;
}

// ---------------- 经营优先级 ----------------

export type PriorityComponentKey =
  | 'PRODUCT_EXECUTION_CAPABILITY'
  | 'RELATIONSHIP'
  | 'INTERVENTION_STAGE'
  | 'PROJECT_AMOUNT';

export interface PriorityComponent {
  key: PriorityComponentKey;
  label: string;
  score: number; // 0-100
}

export interface Priority {
  score: number; // 0-100
  tier: PriorityTier;
  components: PriorityComponent[];
}

// ---------------- AI 行动判断 ----------------

export interface Decision {
  action: string | null;
  reasons: string[];
  risks: string[];
  requires_human_confirmation: boolean;
}

export interface ModelRequest {
  opportunity_id: string;
  status: ModelDecisionStatus;
  requested_at: string;
}

// ---------------- 跟进记录 ----------------

export interface FollowupHistoryEntry {
  id: string;
  status: FollowupStatus;
  note?: string | null;
  not_fit_reason?: NotFitReason | null;
  at: string;
}

export interface FollowupState {
  status: FollowupStatus;
  not_fit_reason?: NotFitReason | null;
  updated_at: string;
  history: FollowupHistoryEntry[];
}

export interface FollowupInput {
  status: FollowupStatus;
  note?: string;
  not_fit_reason?: NotFitReason;
}

// ---------------- 今日行动卡 ----------------

export type MatchStatus = 'MATCHED' | 'CANDIDATE';

export interface TodayActionCard {
  rank: number;
  opportunity_id: string;
  facts: OfficialFacts;
  evidence_source_urls: EvidenceLink[];
  customer_context: CustomerContext;
  priority: Priority;
  match_status: MatchStatus;
  recommendation_mode: string;
  model_decision_status: ModelDecisionStatus;
  model_block_reason?: string | null;
  decision: Decision | null;
  followup: FollowupState;
}

export interface TodayActionsResponse {
  schema_version: '0.1';
  mode: 'TODAY_ACTIONS';
  input_candidate_count: number;
  matched_count: number;
  card_count: number;
  model_request_count: number;
  coverage_warning: string;
  generated_at: string;
  cards: TodayActionCard[];
  model_requests: ModelRequest[];
}

// ---------------- 沟通话术 ----------------

export interface OutreachDraft {
  opportunity_id: string;
  generated_at: string;
  content: string;
  disclaimer: string;
}
