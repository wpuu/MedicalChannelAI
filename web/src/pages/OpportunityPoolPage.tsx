import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BookmarkPlus,
  Check,
  ChevronRight,
  ExternalLink,
  Filter,
  Loader2,
  Search,
  SlidersHorizontal,
} from 'lucide-react'
import { DecisionBlock } from '@/components/today/DecisionBlock'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { PreMarketSignalNotice, isPreMarketSignal } from '@/components/shared/PreMarketSignalNotice'
import { PriorityBadge } from '@/components/shared/PriorityBadge'
import { StageBadge } from '@/components/shared/StageBadge'
import { marketCodesForSelection, marketSelectionLabel } from '@/config/marketPreference'
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import { AiDecisionError, requestAiDecision } from '@/services/aiDecisionApi'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import { persistLocalFollowup } from '@/services/localFollowupStore'
import {
  getRuntimeStatus,
  runtimeAutomationUnavailableReason,
  runtimeSnapshotWarning,
  type RuntimeStatus,
} from '@/services/runtimeStatusApi'
import { getVerifiedOpportunityPool } from '@/services/verifiedOpportunityPool'
import type { TodayActionCard } from '@/types'
import { formatBudget, formatDateTime, uid } from '@/utils/format'

type WindowFilter = 'ALL' | 'OPEN' | 'PRE_MARKET_SIGNAL' | 'LATE_WINDOW'
const AI_UNCONFIGURED_REASON = 'AI运行配置尚未完成；商机检索、官方依据和跟进功能仍可正常使用。'

function normalizedSearchText(card: TodayActionCard): string {
  return [
    card.facts.project_code,
    card.facts.project_name,
    card.facts.hospital,
    card.facts.buyer_name,
    card.facts.department,
    card.facts.market_name,
    card.facts.region,
    ...(card.facts.product_categories ?? []),
    ...(card.facts.products ?? []).flatMap((item) => [item.name, item.category, item.specification]),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function deadlineLabel(card: TodayActionCard): string | null {
  if (card.recommendation_mode === 'LATE_WINDOW' && card.facts.bid_deadline) {
    const formatted = formatDateTime(card.facts.bid_deadline)
    return formatted ? `投标/响应截止 ${formatted}` : null
  }
  if (card.facts.registration_deadline) {
    const formatted = formatDateTime(card.facts.registration_deadline)
    return formatted ? `报名截止 ${formatted}` : null
  }
  if (card.facts.registration_deadline_date) {
    return `报名截止日期 ${card.facts.registration_deadline_date}（未公布具体时间）`
  }
  if (card.facts.bid_deadline) {
    const formatted = formatDateTime(card.facts.bid_deadline)
    return formatted ? `投标/响应截止 ${formatted}` : null
  }
  return null
}

function telHref(value: string | null | undefined): string | null {
  const raw = String(value || '').trim()
  if (!raw || /[、,，;；/]/.test(raw)) return null
  const leadingPlus = raw.startsWith('+')
  const digits = raw.replace(/\D/g, '')
  if (digits.length < 5) return null
  return `tel:${leadingPlus ? '+' : ''}${digits}`
}

function mailtoHref(value: string | null | undefined): string | null {
  const email = String(value || '').trim()
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? `mailto:${email}` : null
}

function aiErrorMessage(cause: unknown): string {
  if (!(cause instanceof AiDecisionError)) return 'AI分析暂时不可用，请稍后重试'
  if (cause.code === 'AI_NOT_CONFIGURED') return 'AI服务端运行配置尚未完成'
  if (cause.code === 'AI_RATE_LIMITED') return 'AI服务当前限流，请稍后再试'
  if (cause.code === 'AI_PROVIDER_AUTH_UNAVAILABLE') return 'AI服务端当前不可用'
  if (cause.code === 'AI_TIMEOUT') return 'AI分析超时，请稍后重试'
  if (cause.code === 'VERIFIED_SNAPSHOT_NOT_FRESH') return '公开商机快照已超过安全刷新窗口，请先核对官方依据，待数据刷新后再分析'
  if (cause.code === 'VERIFIED_SNAPSHOT_UNAVAILABLE') return '当前无法确认公开商机快照，请先核对官方依据，待数据恢复后再分析'
  if (cause.code === 'OPPORTUNITY_WINDOW_CLOSED') return '该项目公开窗口已经结束，当前不再生成行动建议'
  if (cause.code === 'VERIFIED_OPPORTUNITY_NOT_FOUND') return '该商机不在服务端已核验商机池中'
  return 'AI分析暂时不可用，请稍后重试'
}

function PoolCard({
  card,
  aiBusy,
  followBusy,
  onAnalyze,
  onFollow,
  onOpen,
  analysisUnavailableReason,
}: {
  card: TodayActionCard
  aiBusy: boolean
  followBusy: boolean
  onAnalyze?: () => void
  onFollow: () => void
  onOpen: () => void
  analysisUnavailableReason?: string | null
}) {
  const buyer = card.facts.hospital ?? card.facts.buyer_name ?? '采购单位未提供'
  const budget = formatBudget(card.facts.budget)
  const deadline = deadlineLabel(card)
  const late = card.recommendation_mode === 'LATE_WINDOW'
  const preMarket = isPreMarketSignal(card.facts.lifecycle_stage, card.recommendation_mode)
  const followed = card.followup_status !== 'NEW'
  const contact = card.facts.official_contact
  const contactPhone = contact?.phone?.trim() || null
  const contactEmail = contact?.email?.trim() || null
  const contactPhoneHref = telHref(contactPhone)
  const contactEmailHref = mailtoHref(contactEmail)
  const marketName = card.facts.market_name?.trim() || null
  const noticeRegion = card.facts.region?.trim() || null

  return (
    <article className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white">
              #{card.rank}
            </span>
            <PriorityBadge score={card.priority.score} scoreScope={card.priority.score_scope} />
            <StageBadge stage={card.facts.lifecycle_stage} />
            {marketName ? (
              <span className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-800">
                {marketName}
              </span>
            ) : null}
            {late ? (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                报名窗口已结束
              </span>
            ) : null}
          </div>
          <h3 className="mt-2 text-[15px] font-semibold leading-6 text-slate-900">{buyer}</h3>
          <p className="mt-0.5 text-[14px] leading-6 text-slate-700">
            {card.facts.project_name ?? '项目名称未提供'}
          </p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-slate-500">
            {budget ? <span>公开预算 {budget}</span> : <span>公开预算未提供</span>}
            {deadline ? <span>{deadline}</span> : null}
            {noticeRegion && noticeRegion !== marketName ? <span>公告区域 {noticeRegion}</span> : null}
          </div>
          {preMarket ? (
            <div className="mt-2">
              <PreMarketSignalNotice
                lifecycleStage={card.facts.lifecycle_stage}
                recommendationMode={card.recommendation_mode}
                qualityFlags={card.facts.quality_flags}
                compact
              />
            </div>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={followed || followBusy}
              onClick={onFollow}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 text-[12px] font-medium text-teal-800 transition hover:bg-teal-100 disabled:cursor-default disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-500"
            >
              {followBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : followed ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <BookmarkPlus className="h-3.5 w-3.5" />
              )}
              {followBusy ? '正在加入…' : followed ? '已在我的跟进' : '加入我的跟进'}
            </button>
            <button
              type="button"
              onClick={onOpen}
              className="inline-flex min-h-9 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
            >
              完整详情
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-2xl font-semibold tabular-nums text-slate-900">{card.priority.score}</div>
          <div className="text-[11px] text-slate-400">
            {card.priority.score_scope === 'PERSONALIZED' ? '个性化优先级' : '公开优先级'}
          </div>
        </div>
      </div>

      <details className="border-t border-slate-100 px-4 py-3">
        <summary className="cursor-pointer select-none text-[12px] font-medium text-teal-700">
          查看设备、联系人、官方依据和AI判断
        </summary>
        <div className="mt-3 grid gap-4 text-[12px] leading-5 text-slate-600 md:grid-cols-2">
          <div>
            <p className="font-medium text-slate-800">采购内容</p>
            {card.facts.products?.length ? (
              <ul className="mt-1 space-y-1">
                {card.facts.products.slice(0, 12).map((item, index) => (
                  <li key={`${item.name}-${index}`}>• {item.name}</li>
                ))}
                {card.facts.products.length > 12 ? (
                  <li className="text-slate-400">另有 {card.facts.products.length - 12} 项</li>
                ) : null}
              </ul>
            ) : card.facts.product_categories?.length ? (
              <p className="mt-1">{card.facts.product_categories.join('、')}</p>
            ) : (
              <p className="mt-1 text-slate-400">公开页面未结构化出设备明细</p>
            )}
          </div>
          <div>
            <p className="font-medium text-slate-800">公开联系人</p>
            {contact ? (
              <div className="mt-1 space-y-1">
                {contact.name ? <p>{contact.name}</p> : null}
                {contact.title ? <p>{contact.title}</p> : null}
                {contactPhone ? (
                  contactPhoneHref ? (
                    <a
                      href={contactPhoneHref}
                      className="block font-medium text-teal-700 underline decoration-teal-200 underline-offset-2"
                    >
                      电话 {contactPhone}
                    </a>
                  ) : <p>电话 {contactPhone}</p>
                ) : null}
                {contactEmail ? (
                  contactEmailHref ? (
                    <a
                      href={contactEmailHref}
                      className="block break-all font-medium text-teal-700 underline decoration-teal-200 underline-offset-2"
                    >
                      {contactEmail}
                    </a>
                  ) : <p className="break-all">{contactEmail}</p>
                ) : null}
              </div>
            ) : (
              <p className="mt-1 text-slate-400">当前公开事实未提供联系人</p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {card.evidence_source_urls.map((url, index) => (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
                >
                  官方依据 {index + 1}
                  <ExternalLink className="h-3 w-3" />
                </a>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-4">
          <DecisionBlock
            card={card}
            analyzing={aiBusy}
            onAnalyze={onAnalyze}
            analysisUnavailableReason={analysisUnavailableReason}
          />
        </div>
      </details>
    </article>
  )
}

export function OpportunityPoolPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [cards, setCards] = useState<TodayActionCard[]>([])
  const [snapshotAsOf, setSnapshotAsOf] = useState<string | null>(null)
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null)
  const [runtimeStatusChecked, setRuntimeStatusChecked] = useState(false)
  const [query, setQuery] = useState('')
  const [windowFilter, setWindowFilter] = useState<WindowFilter>('ALL')
  const [aiBusyId, setAiBusyId] = useState<string | null>(null)
  const [followBusyId, setFollowBusyId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    const loadPool = async () => {
      if (isApiMode) {
        const data = await todayActionsService.getTodayActions({ hydrateFollowups: false })
        return {
          cards: data.opportunity_pool ?? data.cards,
          snapshot_as_of: data.refreshed_at,
        }
      }
      const result = await getVerifiedOpportunityPool()
      return { cards: result.cards, snapshot_as_of: result.snapshot_as_of }
    }

    void loadPool()
      .then((result) => {
        if (cancelled) return
        setCards(result.cards)
        setSnapshotAsOf(result.snapshot_as_of)
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

    void getRuntimeStatus().then((status) => {
      if (cancelled) return
      setRuntimeStatus(status)
      setRuntimeStatusChecked(true)
    })
    return () => {
      cancelled = true
    }
  }, [navigate])

  const selectedMarketCodes = useMemo(() => new Set(marketCodesForSelection()), [])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return cards.filter((card) => {
      const preMarket = isPreMarketSignal(card.facts.lifecycle_stage, card.recommendation_mode)
      if (!card.facts.market_code || !selectedMarketCodes.has(card.facts.market_code as never)) return false
      if (windowFilter === 'OPEN' && (card.recommendation_mode === 'LATE_WINDOW' || preMarket)) return false
      if (windowFilter === 'PRE_MARKET_SIGNAL' && !preMarket) return false
      if (windowFilter === 'LATE_WINDOW' && card.recommendation_mode !== 'LATE_WINDOW') return false
      if (!needle) return true
      return normalizedSearchText(card).includes(needle)
    })
  }, [cards, query, selectedMarketCodes, windowFilter])

  const addToFollowups = async (id: string) => {
    const card = cards.find((item) => item.opportunity_id === id)
    if (!card || card.followup_status !== 'NEW') return
    setFollowBusyId(id)
    try {
      if (isApiMode) {
        await todayActionsService.updateFollowup(id, {
          status: 'REVIEWING',
          note: '从商机池加入跟进',
        })
        setCards((current) =>
          current.map((item) =>
            item.opportunity_id === id ? { ...item, followup_status: 'REVIEWING' } : item,
          ),
        )
      } else {
        const record = {
          id: uid('fu'),
          status: 'REVIEWING' as const,
          note: '从商机池加入跟进',
          at: new Date().toISOString(),
          actor: '当前用户',
        }
        const next: TodayActionCard = {
          ...card,
          followup_status: 'REVIEWING',
          followup_history: [record, ...card.followup_history],
        }
        persistLocalFollowup(next)
        setCards((current) => current.map((item) => item.opportunity_id === id ? next : item))
      }
      toast('已加入“我的跟进”', 'success')
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('加入跟进失败，请稍后重试')
    } finally {
      setFollowBusyId(null)
    }
  }

  const analyze = async (id: string) => {
    const automationUnavailableReason = runtimeAutomationUnavailableReason(
      runtimeStatus,
      runtimeStatusChecked,
    )
    const card = cards.find((item) => item.opportunity_id === id)
    if (!card || automationUnavailableReason) return
    setAiBusyId(id)
    try {
      const decision = await requestAiDecision(card)
      setCards((current) =>
        current.map((item) =>
          item.opportunity_id === id
            ? {
                ...item,
                model_decision_status: 'READY',
                model_block_reason: null,
                decision,
              }
            : item,
        ),
      )
      toast(
        isApiMode
          ? 'AI已结合已核验公开事实和当前账号资源给出行动建议'
          : 'AI已基于已核验公开事实给出行动建议',
        'success',
      )
    } catch (cause) {
      if (cause instanceof AiDecisionError && cause.code === 'AUTH_REQUIRED') {
        navigate('/login', { replace: true })
        return
      }
      if (cause instanceof AiDecisionError && cause.code === 'AI_NOT_CONFIGURED') {
        setRuntimeStatus((current) =>
          current ? { ...current, ai: { configured: false } } : current,
        )
      }
      toast(aiErrorMessage(cause))
    } finally {
      setAiBusyId(null)
    }
  }

  if (loading) return <LoadingState />
  if (error) {
    return <ErrorState message="商机池加载失败，请稍后重试。" onRetry={() => window.location.reload()} />
  }

  const automationUnavailableReason = runtimeAutomationUnavailableReason(
    runtimeStatus,
    runtimeStatusChecked,
  )
  const snapshotWarning = runtimeSnapshotWarning(runtimeStatus, runtimeStatusChecked)
  const aiUnavailableReason = automationUnavailableReason || (
    runtimeStatus?.ai.configured === false ? AI_UNCONFIGURED_REASON : null
  )

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">全部已核验机会与早期信号</h2>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">
              首页按账号设置展示今日重点；这里保留同一事实快照中全部仍有效正式机会，以及可提前布局但尚未进入正式报名/投标窗口的采购意向。真实账号下使用完整个性化排序，并与“我的跟进”同步。
            </p>
          </div>
          <div className="flex flex-col items-end gap-1 text-[12px] text-slate-500">
            <span>{snapshotAsOf ? `快照 ${formatDateTime(snapshotAsOf) ?? snapshotAsOf}` : null}</span>
            {runtimeStatus ? (
              <span className={runtimeStatus.ai.configured ? 'text-indigo-700' : 'text-amber-700'}>
                {runtimeStatus.ai.configured ? 'AI服务已连接' : 'AI服务待配置'}
              </span>
            ) : null}
          </div>
        </div>

        {snapshotWarning ? (
          <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-5 text-amber-900">
            {snapshotWarning}
          </div>
        ) : null}

        <div className="mt-4 flex flex-col gap-2 lg:flex-row">
          <label className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索医院、项目、设备、科室..."
              className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-[13px] outline-none focus:border-teal-400 focus:bg-white"
            />
          </label>
          <div className="flex h-10 items-center rounded-xl border border-slate-200 bg-slate-50 px-3 text-[12px] text-slate-500">
            <span className="whitespace-nowrap">业务地区：<strong className="font-medium text-slate-700">{marketSelectionLabel()}</strong></span>
          </div>
          <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
            <SlidersHorizontal className="ml-2 h-3.5 w-3.5 text-slate-400" />
            {([
              ['ALL', '全部'],
              ['OPEN', '窗口开放'],
              ['PRE_MARKET_SIGNAL', '提前布局'],
              ['LATE_WINDOW', '晚窗口'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setWindowFilter(value)}
                className={`rounded-lg px-2.5 py-1.5 text-[12px] font-medium ${
                  windowFilter === value ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-3 flex items-center gap-1.5 text-[12px] text-slate-500">
          <Filter className="h-3.5 w-3.5" />
          当前显示 {visible.length} / {cards.length} 条
        </div>
      </section>

      {visible.length ? (
        <div className="space-y-3">
          {visible.map((card) => (
            <PoolCard
              key={card.opportunity_id}
              card={card}
              aiBusy={aiBusyId === card.opportunity_id}
              followBusy={followBusyId === card.opportunity_id}
              onAnalyze={
                aiUnavailableReason ? undefined : () => void analyze(card.opportunity_id)
              }
              analysisUnavailableReason={aiUnavailableReason}
              onFollow={() => void addToFollowups(card.opportunity_id)}
              onOpen={() => navigate(`/opportunity/${card.opportunity_id}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState title="没有符合条件的机会" hint="可以清空搜索词、在顶部切换业务地区或调整窗口筛选。" />
      )}
    </div>
  )
}
