import type {
  CapabilityType,
  FollowupStatus,
  ModelDecisionStatus,
  RelationshipStrength,
} from '@/types'

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
}

export const NOT_FIT_REASONS = [
  '没有对应产品',
  '暂无厂家资源',
  '医院关系太弱',
  '项目金额太小',
  '介入时间太晚',
  '判断竞争对手已锁定',
  '科室不匹配',
  '区域不匹配',
  '不做租赁项目',
  '其他',
] as const

export const LOST_REASONS = [
  '价格/报价竞争失败',
  '产品或参数不匹配',
  '厂家/授权资源不足',
  '医院关系不足',
  '介入时间太晚',
  '竞争对手优势明显',
  '投标/响应执行失败',
  '客户需求或项目变化',
  '主动放弃',
  '其他',
] as const

export const WON_REASONS = [
  '产品或参数匹配',
  '厂家/授权资源有优势',
  '医院关系或沟通推进有效',
  '价格或商务条件有优势',
  '介入时机合适',
  '投标/响应执行到位',
  '方案与客户需求匹配',
  '其他',
] as const

export const PRIORITY_COMPONENT_LABEL: Record<string, string> = {
  PRODUCT_EXECUTION_CAPABILITY: '产品执行能力',
  RELATIONSHIP: '医院关系',
  EXECUTION_FLEXIBILITY: '找货/合作执行能力',
  INTERVENTION_STAGE: '可介入阶段',
  DEADLINE_URGENCY: '截止时间紧迫度',
  PROJECT_AMOUNT: '项目金额',
  PRODUCT_SPECIFICITY: '产品与采购信息明确度',
  PUBLICATION_FRESHNESS: '信息新鲜度',
}

export const RELATIONSHIP_LABEL: Record<RelationshipStrength, string> = {
  STRONG: '强',
  MEDIUM: '中等',
  HISTORICAL: '历史关系',
  WEAK: '弱',
  UNKNOWN: '尚未确认',
  NONE: '尚未确认',
}

export const CAPABILITY_LABEL: Record<CapabilityType, string> = {
  DIRECT: '有直接产品能力，授权待确认',
  NEED_MANUFACTURER: '需临时寻找厂家',
  PARTNER: '可联合其他渠道商',
  DIRECT_AUTHORIZED: '已授权，可直接参与',
  DIRECT_UNCONFIRMED: '有直接产品能力，授权待确认',
  RENTAL_CAPABLE: '具备租赁参与能力',
  CAN_SOURCE_PARTNER: '可寻找合作厂家/渠道',
  SERVICE_ONLY: '仅服务能力',
}

export const MODEL_STATUS_COPY: Record<
  ModelDecisionStatus,
  { title: string; hint: string }
> = {
  READY: {
    title: '下一步行动',
    hint: '按已核验公开事实（及你已确认的资源）用固定规则生成，不代表中标预测。',
  },
  AWAITING_MODEL: {
    title: '下一步行动待生成',
    hint: '按已核验公开事实即时生成，不调用AI、不消耗额度。'
  },
  BLOCKED_GROUNDING: {
    title: '公开依据不足，暂不生成行动建议',
    hint: '缺少足够的官方公开信息，系统不会据此编造行动建议。',
  },
  MODEL_OUTPUT_REJECTED: {
    title: '生成内容未通过事实校验',
    hint: '生成内容无法被已有公开事实支撑，已拒绝展示。',
  },
  NOT_ELIGIBLE: {
    title: '当前不需要行动建议',
    hint: '该商机暂未达到需要生成行动建议的条件。',
  },
}

export function yesNo(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return '未确认'
  return value ? '可以' : '不可以'
}
