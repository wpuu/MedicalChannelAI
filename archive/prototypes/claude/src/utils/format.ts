import type {
  LifecycleStage,
  RelationshipStrength,
  CapabilityType,
  PriorityTier,
  FollowupStatus,
  NotFitReason,
  VerificationStatus,
  CoverageStatus,
  ModelDecisionStatus,
} from '../types/opportunity';

export const EMPTY_TEXT = '暂无公开信息';

export function fmtDate(value: string | null | undefined): string {
  if (!value) return EMPTY_TEXT;
  // 支持纯日期字符串或自然语言时间描述
  const isoLike = /^\d{4}-\d{2}-\d{2}/.test(value);
  if (!isoLike) return value;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY_TEXT;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function fmtCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return EMPTY_TEXT;
  if (value >= 10000) {
    const wan = value / 10000;
    return `约 ${wan % 1 === 0 ? wan.toFixed(0) : wan.toFixed(1)} 万元`;
  }
  return `约 ${value.toLocaleString('zh-CN')} 元`;
}

export const LIFECYCLE_STAGE_LABEL: Record<LifecycleStage, string> = {
  DEMAND_SIGNAL: '需求预告',
  REGISTRATION: '报名中',
  BIDDING: '招标/评标中',
  AWARDED: '已中标公示',
  CONTRACT_EXECUTION: '合同执行中',
  MAINTENANCE_RENEWAL: '维保/续约',
};

export function fmtLifecycleStage(stage: LifecycleStage | null | undefined): string {
  if (!stage) return EMPTY_TEXT;
  return LIFECYCLE_STAGE_LABEL[stage] ?? stage;
}

export const RELATIONSHIP_LABEL: Record<RelationshipStrength, string> = {
  STRONG: '强',
  MEDIUM: '中等',
  WEAK: '弱',
  NONE: '无',
};

export const CAPABILITY_TYPE_LABEL: Record<CapabilityType, string> = {
  DIRECT: '可直接参与',
  NEEDS_SOURCING: '需临时寻找厂家',
  PARTIAL_MATCH: '部分匹配，需评估',
};

export const PRIORITY_TIER_META: Record<PriorityTier, { label: string; className: string; barClassName: string }> = {
  IMMEDIATE: {
    label: '立即关注',
    className: 'bg-rose-50 text-rose-700 border-rose-200',
    barClassName: 'bg-rose-500',
  },
  FOCUS: {
    label: '重点跟进',
    className: 'bg-amber-50 text-amber-700 border-amber-200',
    barClassName: 'bg-amber-500',
  },
  MONITOR: {
    label: '持续观察',
    className: 'bg-sky-50 text-sky-700 border-sky-200',
    barClassName: 'bg-sky-500',
  },
  NORMAL: {
    label: '普通',
    className: 'bg-slate-100 text-slate-600 border-slate-200',
    barClassName: 'bg-slate-400',
  },
};

export function priorityTierFromScore(score: number): PriorityTier {
  if (score >= 90) return 'IMMEDIATE';
  if (score >= 75) return 'FOCUS';
  if (score >= 60) return 'MONITOR';
  return 'NORMAL';
}

export const VERIFICATION_STATUS_LABEL: Record<VerificationStatus, string> = {
  VERIFIED: '已核验',
  UNVERIFIED: '未核验',
  PARTIAL: '部分核验',
};

export const COVERAGE_STATUS_LABEL: Record<CoverageStatus, string> = {
  FULL: '覆盖完整',
  PARTIAL: '覆盖不完整',
  LIMITED: '覆盖有限',
};

export const FOLLOWUP_STATUS_LABEL: Record<FollowupStatus, string> = {
  NEW: '新发现',
  REVIEWING: '正在评估',
  CONTACTED: '已联系',
  RELATIONSHIP_VERIFIED: '关系已确认',
  PREPARING: '准备中',
  BID_SUBMITTED: '已投标',
  WON: '已成交',
  LOST: '未成交',
  NOT_FIT: '不适合',
  MONITOR: '持续观察',
  ARCHIVED: '已归档',
};

export const FOLLOWUP_STATUS_ORDER: FollowupStatus[] = [
  'NEW',
  'REVIEWING',
  'CONTACTED',
  'RELATIONSHIP_VERIFIED',
  'PREPARING',
  'BID_SUBMITTED',
  'WON',
  'LOST',
  'NOT_FIT',
  'MONITOR',
  'ARCHIVED',
];

export const NOT_FIT_REASON_LABEL: Record<NotFitReason, string> = {
  NO_MATCHING_PRODUCT: '没有对应产品',
  NO_VENDOR_RESOURCE: '暂无厂家资源',
  WEAK_HOSPITAL_RELATIONSHIP: '医院关系太弱',
  BUDGET_TOO_SMALL: '项目金额太小',
  TOO_LATE_TO_INTERVENE: '介入时间太晚',
  COMPETITOR_LOCKED_IN: '判断竞争对手已锁定',
  DEPARTMENT_MISMATCH: '科室不匹配',
  REGION_MISMATCH: '区域不匹配',
  NO_LEASING_SUPPORT: '不做租赁项目',
  OTHER: '其他',
};

export const NOT_FIT_REASON_ORDER: NotFitReason[] = [
  'NO_MATCHING_PRODUCT',
  'NO_VENDOR_RESOURCE',
  'WEAK_HOSPITAL_RELATIONSHIP',
  'BUDGET_TOO_SMALL',
  'TOO_LATE_TO_INTERVENE',
  'COMPETITOR_LOCKED_IN',
  'DEPARTMENT_MISMATCH',
  'REGION_MISMATCH',
  'NO_LEASING_SUPPORT',
  'OTHER',
];

export const MODEL_DECISION_STATUS_META: Record<
  ModelDecisionStatus,
  { title: string; description: string; tone: 'ready' | 'waiting' | 'blocked' | 'rejected' | 'skip' }
> = {
  READY: { title: 'AI行动建议', description: '', tone: 'ready' },
  AWAITING_MODEL: { title: 'AI分析排队中', description: '系统正在处理，请稍后查看', tone: 'waiting' },
  BLOCKED_GROUNDING: {
    title: '公开依据不足，暂不生成AI建议',
    description: '当前官方信息不足以支撑可靠判断',
    tone: 'blocked',
  },
  MODEL_OUTPUT_REJECTED: {
    title: 'AI输出未通过事实校验',
    description: '系统已拦截该建议，需人工复核',
    tone: 'rejected',
  },
  NOT_ELIGIBLE: { title: '当前不需要AI建议', description: '', tone: 'skip' },
};
