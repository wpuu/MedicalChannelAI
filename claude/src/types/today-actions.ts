// ============================================================
// MedicalChannelAI · 核心数据结构定义
// 严格区分：官方事实 / 官方依据 / 客户自有资源 / AI建议
// ============================================================

/** 商机与客户产品能力的匹配状态 */
export type MatchStatus = "MATCHED" | "PARTIAL" | "UNMATCHED" | "PENDING";

/** AI 模型处理状态 */
export type ModelDecisionStatus =
  | "READY" // 已生成建议
  | "AWAITING_MODEL" // 排队等待模型分析
  | "BLOCKED_GROUNDING" // 官方依据不足，无法生成建议
  | "MODEL_OUTPUT_REJECTED" // 模型输出未通过校验，已拦截
  | "NOT_ELIGIBLE"; // 不满足纳入分析的前置条件

/** AI 建议生成方式 */
export type RecommendationMode =
  | "ai_generated"
  | "rule_based"
  | "manual_review"
  | "unavailable";

/** 关系强度 */
export type RelationshipLevel = "强关系" | "一般关系" | "弱关系" | "无关系";

/** 经营优先级分层 */
export type PriorityTier = "立即关注" | "重点跟进" | "持续观察" | "暂不推荐";

/** ------------------------------------------------------------
 * 官方事实：只能来自公开渠道，没有数据一律显示"暂无公开信息"
 * ------------------------------------------------------------ */
export interface ProjectFacts {
  hospital_name: string | null;
  project_name: string | null;
  project_stage: string | null; // 例如：意向公示 / 招标公告 / 评标中 / 中标公示
  budget_amount: string | null; // 例如：约 380 万元
  procurement_category: string[]; // 采购产品类别
  deadline_or_expected_date: string | null; // 截止日期 / 预计采购时间
  official_contact: string | null; // 公开联系人（若有公示）
  region: string;
  announcement_date: string | null; // 公告发布日期
}

/** 官方依据来源 */
export interface EvidenceSource {
  label: string;
  url: string;
  published_at?: string | null;
}

/** ------------------------------------------------------------
 * 客户自有资源：客户确认信息，非官方公告
 * ------------------------------------------------------------ */
export interface CustomerContext {
  has_hospital_relationship: boolean;
  relationship_level: RelationshipLevel;
  related_department: string | null; // 关系科室
  internal_contact: string | null; // 内部负责人 / 线人
  matched_products: string[]; // 我方匹配产品能力
  brand: string | null;
  can_find_vendor_partner: boolean; // 是否可寻找厂家/渠道合作
  notes: string | null;
}

/** 经营优先级评分（非中标概率） */
export interface OpportunityPriority {
  score: number; // 0-100
  tier: PriorityTier;
  reasons: string[];
}

/** AI 行动建议（不含中标概率） */
export interface AIDecision {
  status: ModelDecisionStatus;
  recommended_action: string | null;
  reason: string | null;
  risk: string | null;
}

/** 跟进记录 */
export interface FollowUpRecord {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  note?: string;
}

/** Today Actions 卡片：单个商机的完整视图模型 */
export interface TodayActionCard {
  rank: number;
  opportunity_id: string;
  facts: ProjectFacts;
  evidence_source_urls: EvidenceSource[];
  customer_context: CustomerContext;
  priority: OpportunityPriority;
  match_status: MatchStatus;
  recommendation_mode: RecommendationMode;
  model_decision_status: ModelDecisionStatus;
  model_block_reason: string | null;
  decision: AIDecision;
  follow_up_records: FollowUpRecord[];
}

/** 今日行动概览统计 */
export interface TodaySummaryStats {
  total_candidates: number; // 今日候选
  matched_opportunities: number; // 匹配商机
  today_focus: number; // 今日重点（立即关注+重点跟进）
  awaiting_ai: number; // AI待分析（非 READY）
}
