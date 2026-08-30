export type ModelDecisionStatus =
  | "READY"
  | "AWAITING_MODEL"
  | "BLOCKED_GROUNDING"
  | "MODEL_OUTPUT_REJECTED"
  | "NOT_ELIGIBLE";

export type MatchStatus =
  | "STRONG_RELATION_DIRECT_PRODUCT"
  | "WEAK_RELATION_DIRECT_PRODUCT"
  | "STRONG_RELATION_NEED_MANUFACTURER"
  | "NO_RELATION_DIRECT_PRODUCT"
  | "WEAK_RELATION_NEED_MANUFACTURER";

export type RecommendationMode = "FOLLOW_NOW" | "OBSERVE" | "NOT_RECOMMENDED";

export type FollowUpAction =
  | "contacted"
  | "following"
  | "not_fit"
  | "remind_later";

export type RelationshipStrength = "strong" | "weak" | "none";

export interface Facts {
  hospital_name: string | null;
  purchaser: string | null;
  project_name: string | null;
  project_stage: string | null;
  budget: string | null;
  deadline: string | null;
  expected_purchase_time: string | null;
  products: string[] | null;
  public_contact: string | null;
  public_contact_phone: string | null;
  announcement_date: string | null;
  region: string | null;
  notice_summary: string | null;
}

export interface CustomerContext {
  hospital_relationship: string | null;
  related_department: string | null;
  internal_owner: string | null;
  product_capability: string | null;
  brand: string | null;
  can_find_manufacturer: boolean;
  can_channel_cooperate: boolean;
  relationship_strength: RelationshipStrength;
  has_direct_product: boolean;
  notes: string | null;
}

export interface Priority {
  score: number;
  label: string;
}

export interface Decision {
  suggested_action: string;
  reason: string;
  risk: string;
}

export interface FollowUpRecord {
  id: string;
  opportunity_id: string;
  action: FollowUpAction;
  note: string;
  created_at: string;
  remind_at: string | null;
}

export interface CardActionState {
  action: FollowUpAction | null;
  remind_at: string | null;
  updated_at: string | null;
}

export interface CommunicationScript {
  title: string;
  disclaimer: string;
  opening: string;
  value_points: string[];
  questions: string[];
  closing: string;
  cautions: string[];
  based_on: string[];
  uses_ai_decision: boolean;
}

export interface TodayActionCard {
  rank: number;
  opportunity_id: string;
  facts: Facts;
  evidence_source_urls: string[];
  customer_context: CustomerContext;
  priority: Priority;
  match_status: MatchStatus;
  recommendation_mode: RecommendationMode;
  model_decision_status: ModelDecisionStatus;
  model_block_reason: string | null;
  decision: Decision | null;
}

export interface TodayActionsSummary {
  candidate_count: number;
  matched_count: number;
  focus_count: number;
  awaiting_ai_count: number;
  region: string;
  updated_label: string;
}

export interface TodayActionsPayload {
  summary: TodayActionsSummary;
  cards: TodayActionCard[];
}
