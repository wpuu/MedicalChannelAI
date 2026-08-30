import { demoDatasetMode } from '@/config/demoDataset'
import { mockTodayActionsResponse } from '@/data/today-actions.mock'
import { verifiedDemoTodayActionsResponse } from '@/data/today-actions.verified-demo'
import type {
  FollowupInput,
  FollowupRecord,
  OutreachDraft,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'
import { formatBudget, formatDate, uid } from '@/utils/format'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL } from '@/utils/labels'
import type { TodayActionsService } from './TodayActionsService'

const SYNTHETIC_STORAGE_KEY = 'medopp.followups.v1'
const VERIFIED_STORAGE_KEY = 'medopp.verified-followups.v1'
const STORAGE_KEY = demoDatasetMode === 'verified' ? VERIFIED_STORAGE_KEY : SYNTHETIC_STORAGE_KEY
const selectedDemoResponse =
  demoDatasetMode === 'verified' ? verifiedDemoTodayActionsResponse : mockTodayActionsResponse

export function resetMockDemoState(): void {
  try {
    localStorage.removeItem(SYNTHETIC_STORAGE_KEY)
    localStorage.removeItem(VERIFIED_STORAGE_KEY)
  } catch {
    // A browser that blocks localStorage still has a usable in-memory Demo.
  }
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

interface StoredFollowup {
  status: TodayActionCard['followup_status']
  remind_at: string | null
  history: FollowupRecord[]
}

export class MockTodayActionsService implements TodayActionsService {
  private snapshot: TodayActionsResponse

  constructor() {
    this.snapshot = clone(selectedDemoResponse)
    this.hydrateFollowups()
  }

  private hydrateFollowups() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const map = JSON.parse(raw) as Record<string, StoredFollowup>
      this.snapshot.cards = this.snapshot.cards.map((card) => {
        const saved = map[card.opportunity_id]
        if (!saved) return card
        return {
          ...card,
          followup_status: saved.status,
          remind_at: saved.remind_at,
          followup_history: saved.history?.length ? saved.history : card.followup_history,
        }
      })
    } catch {
      // ignore broken local cache
    }
  }

  private persistFollowups() {
    const map: Record<string, StoredFollowup> = {}
    for (const card of this.snapshot.cards) {
      map[card.opportunity_id] = {
        status: card.followup_status,
        remind_at: card.remind_at,
        history: card.followup_history,
      }
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
  }

  async getTodayActions(): Promise<TodayActionsResponse> {
    await wait(420)
    if (demoDatasetMode === 'verified') {
      return clone(this.snapshot)
    }
    return clone({
      ...this.snapshot,
      model_request_count: 0,
      refreshed_at: new Date(Date.now() - 16 * 60 * 1000).toISOString(),
      generated_at: new Date(Date.now() - 24 * 60 * 1000).toISOString(),
    })
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    await wait(280)
    const card = this.snapshot.cards.find((item) => item.opportunity_id === id)
    return card ? clone(card) : null
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    await wait(180)
    const card = this.snapshot.cards.find((item) => item.opportunity_id === id)
    if (!card) {
      throw new Error('未找到对应商机')
    }
    const record: FollowupRecord = {
      id: uid('fu'),
      status: input.status,
      note: input.note,
      reason: input.reason,
      remind_at: input.remind_at,
      at: new Date().toISOString(),
      actor: '当前用户',
    }
    card.followup_status = input.status
    card.remind_at = input.remind_at ?? (input.status === 'MONITOR' ? card.remind_at : null)
    if (input.remind_at) {
      card.remind_at = input.remind_at
    }
    card.followup_history = [record, ...card.followup_history]
    this.persistFollowups()
  }

  async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    await wait(720)
    const card = this.snapshot.cards.find((item) => item.opportunity_id === id)
    if (!card) {
      throw new Error('未找到对应商机')
    }
    if (
      card.model_decision_status === 'BLOCKED_GROUNDING' ||
      card.model_decision_status === 'NOT_ELIGIBLE' ||
      card.evidence_source_urls.length === 0
    ) {
      throw new Error('OUTREACH_GROUNDING_INSUFFICIENT')
    }
    return {
      opportunity_id: id,
      disclaimer:
        demoDatasetMode === 'verified'
          ? '真实公开事实快照 + 演示客户资源 · 话术由页面内演示逻辑生成，不代表实时 Agnes 调用，不代表医院立场。正式版将根据已验证事实和客户真实资源按需生成。'
          : '演示模式 · 正式版将根据当前商机事实和客户资源按需生成。本话术仅供内部沟通参考，不是官方公告，也不代表医院立场。',
      generated_at: new Date().toISOString(),
      draft: buildDraft(card),
    }
  }
}

function buildDraft(card: TodayActionCard): string {
  const hospital = card.facts.hospital ?? card.facts.buyer_name ?? '对方单位'
  const project = card.facts.project_name ?? '相关采购项目'
  const dept = card.facts.department ?? '相关科室'
  const owner = card.customer_context.hospital_relationship?.owner ?? '我们团队'
  const contact = card.facts.official_contact?.name
  const greeting = contact ? `${contact}老师` : `${dept}老师`
  const rel = card.customer_context.hospital_relationship
  const relLine = rel
    ? `演示客户画像中，与贵院${rel.department ?? ''}的关系强度为：${RELATIONSHIP_LABEL[rel.relationship_strength]}（演示内部负责人：${rel.owner ?? '未指定'}）。实际使用时必须由客户确认后才能这样引用。`
    : '当前演示客户画像尚未确认院内关系，本次沟通以了解需求与时间节点为主。'
  const capability = card.customer_context.matching_product_capabilities[0]
  const capLine = capability
    ? `演示客户画像在${capability.subcategory ?? capability.category}方向的能力是：${CAPABILITY_LABEL[capability.capability_type]}${capability.brands.length ? `（${capability.brands.join('、')}）` : ''}。`
    : '当前演示客户画像中暂无明确匹配产品，需先确认真实供给能力。'
  const budget = formatBudget(card.facts.budget)
  const deadline =
    formatDate(card.facts.bid_deadline) ??
    formatDate(card.facts.registration_deadline) ??
    formatDate(card.facts.expected_purchase_date)
  const factBits = [
    card.facts.lifecycle_stage ? `项目阶段：${card.facts.lifecycle_stage}` : null,
    budget ? `公开预算：${budget}` : null,
    deadline ? `关键时间：${deadline}` : null,
  ].filter(Boolean)

  return [
    `【内部沟通话术草稿】`,
    ``,
    `${greeting}您好：`,
    ``,
    `我是${owner}。关注到${hospital}${card.facts.department ? dept : ''}正在推进「${project}」。`,
    factBits.length ? `目前可引用的公开信息包括：${factBits.join('；')}。` : `目前可引用的公开信息有限，沟通时请只陈述已核实内容，不要补充未公开细节。`,
    ``,
    relLine,
    capLine,
    ``,
    `想进一步确认当前需求范围、时间安排以及后续资料对接窗口。如方便，我们再根据实际需求准备对应方案。`,
    ``,
    `谢谢。`,
    ``,
    `——`,
    `说明：公开项目事实与客户侧资源必须分开核实；以上客户关系/能力在演示版中属于演示画像。`,
  ].join('\n')
}
