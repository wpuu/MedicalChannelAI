import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Building2, ExternalLink, Loader2, Radar, SearchCheck } from 'lucide-react'
import {
  expectedProcurementWindowPhase,
  expectedProcurementWindowText,
  isPreMarketSignal,
} from '@/components/shared/PreMarketSignalNotice'
import { EmptyState, ErrorState } from '@/components/shared/PageStates'
import { todayActionsService } from '@/services'
import { isAuthRequiredError } from '@/services/apiConfig'
import type { TodayActionCard } from '@/types'

const GENERIC_PRODUCT_TERMS = new Set([
  '医疗设备',
  '医疗器械',
  '设备',
  '耗材',
  '试剂',
  '服务',
  '采购项目',
  '设备采购项目',
  '医疗设备采购项目',
  '医疗器械采购项目',
])

function normalizeText(value: string | null | undefined): string {
  return String(value || '')
    .toLowerCase()
    .replace(/[\s·•,，。；;：:、()（）【】\[\]《》<>“”"'\/\\_-]+/g, '')
}

function institutionKey(card: TodayActionCard): string {
  return normalizeText(card.facts.hospital ?? card.facts.buyer_name)
}

function productTerms(card: TodayActionCard): string[] {
  const institution = institutionKey(card)
  const values = [
    ...(card.facts.product_categories ?? []),
    ...(card.facts.products ?? []).flatMap((item) => [item.name, item.category]),
  ]
  const result = new Set<string>()
  for (const value of values) {
    let term = normalizeText(value)
    if (!term) continue
    if (institution && term.includes(institution)) term = term.replace(institution, '')
    if (term.length < 2 || GENERIC_PRODUCT_TERMS.has(term)) continue
    result.add(term)
  }
  return [...result]
}

function publicationTime(card: TodayActionCard): number | null {
  if (!card.facts.publish_date) return null
  const parsed = Date.parse(card.facts.publish_date)
  return Number.isNaN(parsed) ? null : parsed
}

function matchedTerms(left: TodayActionCard, right: TodayActionCard): string[] {
  const leftTerms = productTerms(left)
  const rightTerms = productTerms(right)
  const matches = new Set<string>()
  for (const leftTerm of leftTerms) {
    for (const rightTerm of rightTerms) {
      const exact = leftTerm === rightTerm
      const contained =
        Math.min(leftTerm.length, rightTerm.length) >= 4 &&
        (leftTerm.includes(rightTerm) || rightTerm.includes(leftTerm))
      if (exact || contained) matches.add(leftTerm.length <= rightTerm.length ? leftTerm : rightTerm)
    }
  }
  return [...matches].slice(0, 3)
}

function successorCandidates(intent: TodayActionCard, cards: TodayActionCard[]) {
  const institution = institutionKey(intent)
  const intentPublished = publicationTime(intent)
  if (!institution || intentPublished === null) return []

  return cards
    .filter((candidate) => candidate.opportunity_id !== intent.opportunity_id)
    .filter((candidate) => !isPreMarketSignal(candidate.facts.lifecycle_stage, candidate.recommendation_mode))
    .filter((candidate) => institutionKey(candidate) === institution)
    .map((candidate) => ({
      card: candidate,
      published: publicationTime(candidate),
      terms: matchedTerms(intent, candidate),
    }))
    .filter((item) => item.published !== null && item.published >= intentPublished && item.terms.length > 0)
    .sort((left, right) => (left.published ?? 0) - (right.published ?? 0))
    .slice(0, 3)
}

function phaseOrder(card: TodayActionCard): number {
  const window = expectedProcurementWindowText(card.facts.quality_flags)
  const phase = expectedProcurementWindowPhase(window)
  if (phase === 'AFTER') return 0
  if (phase === 'ACTIVE') return 1
  if (phase === 'BEFORE') return 2
  return 3
}

function phaseLabel(card: TodayActionCard): string {
  const window = expectedProcurementWindowText(card.facts.quality_flags)
  const phase = expectedProcurementWindowPhase(window)
  if (phase === 'AFTER') return '预计采购月份已过，优先核查后续公告'
  if (phase === 'ACTIVE') return '已进入预计采购月份，重点盯正式公告'
  if (phase === 'BEFORE') return '预计采购月份未到，继续提前布局'
  return '未结构化出预计采购月份，持续观察'
}

export function ProcurementIntentFollowupPage() {
  const navigate = useNavigate()
  const [cards, setCards] = useState<TodayActionCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    void todayActionsService.getTodayActions({ hydrateFollowups: false })
      .then((data) => {
        if (cancelled) return
        setCards(data.opportunity_pool ?? data.cards)
        setError(false)
      })
      .catch((cause) => {
        if (cancelled) return
        if (isAuthRequiredError(cause)) {
          navigate('/login', { replace: true })
          return
        }
        setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [navigate])

  const rows = useMemo(() => {
    return cards
      .filter((card) => isPreMarketSignal(card.facts.lifecycle_stage, card.recommendation_mode))
      .map((intent) => ({ intent, successors: successorCandidates(intent, cards) }))
      .sort((left, right) => {
        const phaseDiff = phaseOrder(left.intent) - phaseOrder(right.intent)
        if (phaseDiff !== 0) return phaseDiff
        return (publicationTime(right.intent) ?? 0) - (publicationTime(left.intent) ?? 0)
      })
  }, [cards])

  if (loading) {
    return (
      <div className="flex min-h-56 items-center justify-center text-sm text-slate-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        正在核查采购意向与后续正式商机…
      </div>
    )
  }
  if (error) {
    return <ErrorState message="采购意向跟进视图加载失败，请稍后重试。" onRetry={() => window.location.reload()} />
  }
  if (rows.length === 0) {
    return <EmptyState title="当前没有可跟进的采购意向" hint="后续核验到新的采购意向后，会在这里自动进入跟进视图。" />
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex items-start gap-3">
          <Radar className="mt-0.5 h-5 w-5 shrink-0 text-teal-700" />
          <div>
            <h1 className="text-lg font-semibold text-slate-900">采购意向跟进</h1>
            <p className="mt-1 text-[12px] leading-5 text-slate-600">
              系统只用已核验公开事实做保守关联：同一采购单位、明确产品重合、后续公告发布时间不早于采购意向。关联结果只是“可能承接的后续项目”，不是官方声明为同一项目，最终仍需人工核对项目编号、科室、产品和公告原文。
            </p>
          </div>
        </div>
      </section>

      {rows.map(({ intent, successors }) => {
        const buyer = intent.facts.hospital ?? intent.facts.buyer_name ?? '采购单位未提供'
        const expectedWindow = expectedProcurementWindowText(intent.facts.quality_flags)
        return (
          <section key={intent.opportunity_id} className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[11px] font-medium text-amber-800">
                  <Building2 className="h-3.5 w-3.5" />
                  {buyer}
                </div>
                <h2 className="mt-1 text-[15px] font-semibold leading-6 text-slate-900">
                  {intent.facts.project_name ?? '采购意向名称未提供'}
                </h2>
                <p className="mt-1 text-[12px] leading-5 text-slate-600">
                  {expectedWindow ? `官方预计采购时间：${expectedWindow} · ` : ''}{phaseLabel(intent)}
                </p>
              </div>
              <Link
                to={`/opportunity/${encodeURIComponent(intent.opportunity_id)}`}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
              >
                查看意向原文与详情
                <ExternalLink className="h-3 w-3" />
              </Link>
            </div>

            <div className="mt-3 rounded-xl bg-slate-50 px-3 py-3">
              <div className="flex items-center gap-2">
                <SearchCheck className="h-4 w-4 text-teal-700" />
                <p className="text-[12px] font-semibold text-slate-800">
                  {successors.length > 0
                    ? `发现 ${successors.length} 条可能的后续正式商机`
                    : '当前未发现满足保守关联规则的后续正式商机'}
                </p>
              </div>
              {successors.length > 0 ? (
                <div className="mt-2 space-y-2">
                  {successors.map(({ card, terms }) => (
                    <Link
                      key={card.opportunity_id}
                      to={`/opportunity/${encodeURIComponent(card.opportunity_id)}`}
                      className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5 hover:border-teal-200 hover:bg-teal-50/40"
                    >
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium leading-5 text-slate-900">
                          {card.facts.project_name ?? '正式项目名称未提供'}
                        </p>
                        <p className="mt-1 text-[11px] leading-5 text-slate-500">
                          匹配依据：同一采购单位 · 产品重合 {terms.join('、')}
                          {card.facts.publish_date ? ` · 发布 ${card.facts.publish_date}` : ''}
                        </p>
                      </div>
                      <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-teal-700" />
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-[11px] leading-5 text-slate-500">
                  这不代表项目取消或没有后续。可能是正式公告尚未发布、当前公开源尚未覆盖，或后续公告产品字段不足以安全自动关联。继续监控时不要把“未发现关联”当成业务结论。
                </p>
              )}
            </div>
          </section>
        )
      })}
    </div>
  )
}
