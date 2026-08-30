import type {
  FollowUpAction,
  MatchStatus,
  ModelDecisionStatus,
  RecommendationMode,
  RelationshipStrength,
} from "@/types/today-actions";

export const MODEL_STATUS_LABEL: Record<ModelDecisionStatus, string> = {
  READY: "AI建议已就绪",
  AWAITING_MODEL: "AI分析中",
  BLOCKED_GROUNDING: "依据不足，暂无法分析",
  MODEL_OUTPUT_REJECTED: "AI输出未通过校验",
  NOT_ELIGIBLE: "暂不纳入AI分析",
};

export const MODEL_STATUS_HINT: Record<ModelDecisionStatus, string> = {
  READY: "已基于公开信息与我的资源生成行动建议，供销售安排下一步。",
  AWAITING_MODEL: "正在等待模型分析，当前不展示行动建议，避免把猜测当成结论。",
  BLOCKED_GROUNDING: "公开依据不足以支撑判断，系统已阻断建议输出。",
  MODEL_OUTPUT_REJECTED: "模型输出未通过校验，可能包含超出公开信息的推断，已拒绝展示。",
  NOT_ELIGIBLE: "该项目暂不符合分析条件，不生成AI行动建议。",
};

export const MATCH_STATUS_LABEL: Record<MatchStatus, string> = {
  STRONG_RELATION_DIRECT_PRODUCT: "强医院关系 · 可直接供货",
  WEAK_RELATION_DIRECT_PRODUCT: "弱关系 · 可直接供货",
  STRONG_RELATION_NEED_MANUFACTURER: "强医院关系 · 需找厂家",
  NO_RELATION_DIRECT_PRODUCT: "暂无医院关系 · 可直接供货",
  WEAK_RELATION_NEED_MANUFACTURER: "弱关系 · 需找厂家",
};

export const RECOMMENDATION_MODE_LABEL: Record<RecommendationMode, string> = {
  FOLLOW_NOW: "建议今日跟进",
  OBSERVE: "持续观察",
  NOT_RECOMMENDED: "暂不建议投入",
};

export const RELATIONSHIP_LABEL: Record<RelationshipStrength, string> = {
  strong: "强关系",
  weak: "弱关系",
  none: "暂无医院关系",
};

export const FOLLOW_UP_LABEL: Record<FollowUpAction, string> = {
  contacted: "已联系",
  following: "继续跟进",
  not_fit: "不适合",
  remind_later: "稍后提醒",
};

export const PRIORITY_DISCLAIMER =
  "经营优先级，用于安排销售资源，不代表中标概率。";

export const PRIORITY_DISCLAIMER_SHORT = "经营优先级 · 非中标概率";

export const CUSTOMER_CONTEXT_BANNER = "我的资源 · 客户确认信息 · 非官方公告";

export const EMPTY_FACT = "暂无公开信息";

export const DEMO_BANNER = "演示数据";

export const PILOT_NOTE = "当前天津Pilot，公开数据覆盖持续扩展中";

export function getPriorityLabel(score: number): string {
  if (score >= 90) return "立即关注";
  if (score >= 75) return "重点跟进";
  if (score >= 60) return "持续观察";
  return "低优先级";
}

export function getPriorityTone(
  score: number,
): "high" | "mid" | "low" | "muted" {
  if (score >= 90) return "high";
  if (score >= 75) return "mid";
  if (score >= 60) return "low";
  return "muted";
}
