import { mockTodayActionsResponse } from '@/data/today-actions.mock'
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

const STORAGE_KEY = 'medopp.followups.v1'

export function resetMockDemoState(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
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
    this.snapshot = clone(mockTodayActionsResponse)
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
    return clone({
      ...this.snapshot,
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
    return {
      opportunity_id: id,
      disclaimer: '演示模式 · 正式版将根据当前商机事实和客户资源按需生成。本话术仅供内部沟通参考，不是官方公告，也不代表医院立场。',
      generated_at: new Date().toISOString(),
      draft: buildDraft(card),
    }
  }
}

function buildDraft(card: TodayActionCard): string {
  const hospital = card.facts.hospital ?? '对方单位'
  const project = card.facts.project_name ?? '相关采购项目'
  const dept = card.facts.department ?? '相关科室'
  const owner = card.customer_context.hospital_relationship?.owner ?? '我们团队'
  const contact = card.facts.official_contact?.name
  const greeting = contact ? `${contact}老师` : `${dept}老师`
  const rel = card.customer_context.hospital_relationship
  const relLine = rel
    ? `我们与贵院${rel.department ?? ''}保持沟通（关系强度：${RELATIONSHIP_LABEL[rel.relationship_strength]}，内部负责人：${rel.owner ?? '未指定'}）。`
    : '目前尚未确认院内关系，本次沟通以了解需求与时间节点为主。'
  const capability = card.customer_context.matching_product_capabilities[0]
  const capLine = capability
    ? `在${capability.subcategory ?? capability.category}方向，我们的能力是：${CAPABILITY_LABEL[capability.capability_type]}${capability.brands.length ? `（${capability.brands.join('、')}）` : ''}。`
    : '当前客户资源中暂无明确匹配产品，需先内部确认可供方案。'
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
    `我是${owner}。关注到${hospital}${dept}正在推进「${project}」。`,
    factBits.length ? `目前公开信息包括：${factBits.join('；')}。` : `目前可引用的公开信息有限，沟通时请只陈述已核实内容，不要补充未公开细节。`,
    ``,
    relLine,
    capLine,
    ``,
    `想和您确认两件事：一是当前需求范围与时间安排；二是后续资料对接窗口。如方便，我可以按贵院节奏准备方案说明。`,
    ``,
    `谢谢。`,
    ``,
    `——`,
    `说明：以上内容根据公开事实与客户自有资源起草，不得当作医院官方信息转发。`,
  ].join('\n')
}
