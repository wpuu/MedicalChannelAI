import type { ModelDecisionStatus, PriorityTier, RelationshipLevel } from "../types/today-actions";

export interface StatusDisplay {
  label: string;
  description: string;
  className: string; // 徽章配色
  dotClassName: string;
}

/** AI 模型处理状态 → 中文自然语言展示 */
export const MODEL_STATUS_DISPLAY: Record<ModelDecisionStatus, StatusDisplay> = {
  READY: {
    label: "AI建议已生成",
    description: "已基于官方依据与客户资源生成行动建议",
    className: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    dotClassName: "bg-emerald-500",
  },
  AWAITING_MODEL: {
    label: "排队等待AI分析",
    description: "已进入分析队列，暂未生成建议",
    className: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
    dotClassName: "bg-slate-400",
  },
  BLOCKED_GROUNDING: {
    label: "官方依据不足，已阻断AI建议",
    description: "为避免误导，系统未生成行动建议",
    className: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    dotClassName: "bg-amber-500",
  },
  MODEL_OUTPUT_REJECTED: {
    label: "AI输出未通过校验",
    description: "模型建议与官方事实存在冲突，已拦截并转人工复核",
    className: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
    dotClassName: "bg-rose-500",
  },
  NOT_ELIGIBLE: {
    label: "暂不满足分析条件",
    description: "该商机当前不纳入AI建议生成范围",
    className: "bg-slate-100 text-slate-500 ring-1 ring-slate-200",
    dotClassName: "bg-slate-300",
  },
};

export const PRIORITY_TIER_DISPLAY: Record<PriorityTier, { label: string; className: string }> = {
  立即关注: { label: "立即关注", className: "bg-rose-600 text-white" },
  重点跟进: { label: "重点跟进", className: "bg-orange-500 text-white" },
  持续观察: { label: "持续观察", className: "bg-sky-600 text-white" },
  暂不推荐: { label: "暂不推荐", className: "bg-slate-400 text-white" },
};

export const RELATIONSHIP_LEVEL_DISPLAY: Record<RelationshipLevel, string> = {
  强关系: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  一般关系: "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
  弱关系: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  无关系: "bg-slate-100 text-slate-500 ring-1 ring-slate-200",
};

export function priorityTierFromScore(score: number): PriorityTier {
  if (score >= 90) return "立即关注";
  if (score >= 75) return "重点跟进";
  if (score >= 60) return "持续观察";
  return "暂不推荐";
}

export function fallbackText(value: string | null | undefined): string {
  if (!value || value.trim() === "") return "暂无公开信息";
  return value;
}
