import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, Info, Loader2, Radar, Sparkles } from 'lucide-react'
import { ActionCard } from '@/components/today/ActionCard'
import { DueRemindersPanel } from '@/components/today/DueRemindersPanel'
import { MetricCards } from '@/components/today/MetricCards'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { NotFitModal } from '@/components/followup/NotFitModal'
import { RemindModal } from '@/components/followup/RemindModal'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { marketSelectionLabel } from '@/config/marketPreference'
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import { getOpportunityFeedback } from '@/services/opportunityFeedbackStore'
import {
  acknowledgeDueReminder,
  getDueReminders,
  type DueReminder,
} from '@/services/reminderApi'
import {
  getRuntimeStatus,
  runtimeAutomationUnavailableReason,
  runtimeSnapshotWarning,
  type RuntimeStatus,
} from '@/services/runtimeStatusApi'
import type {
  FollowupStatus,
  NotFitReason,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'
import { formatDateTime } from '@/utils/format'

const OutreachDrawer = lazy(() =>
  import('@/components/followup/OutreachDrawer').then((module) => ({ default: module.OutreachDrawer })),
)

const DONE_FOR_TODAY = new Set<FollowupStatus>([
  'CONTACTED',
  'NOT_FIT',
  'BID_SUBMITTED',
  'WON',
  'LOST',
  'ARCHIVED',
])
const MAX_TODAY_CARDS = 5
const AI_UNCONFIGURED_REASON = '已有核验AI建议会直接复用；尚未生成过AI建议的商机暂不实时调用模型。'

function shouldHideFromVerifiedTrialToday(card: TodayActionCard): boolean {
  if (DONE_FOR_TODAY.has(card.followup_status)) return true
  if (!card.remind_at) return false
  const remindAt = new Date(card.remind_at).getTime()
  return !Number.isNaN(remindAt) && remindAt > Date.now()
}

function localDiscoveryFeedbackBucket(card: TodayActionCard): number {
  if (card.followup_status !== 'NEW' || card.remind_at) return 0
  return getOpportunityFeedback(card.opportunity_id) === 'ALREADY_KNOWN' ? 1 : 0
}

function localFeedbackHidesFromToday(card: TodayActionCard): boolean {
  return card.followup_status === 'NEW' &&
    !card.remind_at &&
    getOpportunityFeedback(card.opportunity_id) === 'NEW_NOT_VALUABLE'
}

function userCoverageWarning(value: string): string {
  return value
    .replace(
      '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。',
      '当前业务地区 · 商机来自已核验官方公开信息；各地区仍为部分来源覆盖。',
    )
    .split('天津 Pilot').join('当前业务地区')
    .split('天津公开采购').join('当前业务地区')
}

export function TodayPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [data, setData] = useState<TodayActionsResponse | null>(null)
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null)
  const [runtimeStatusChecked, setRuntimeStatusChecked] = useState(false)
  const [reminders, setReminders] = useState<DueReminder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [aiBusyId, setAiBusyId] = useState<string | null>(null)
  const [aiBatchBusy, setAiBatchBusy] = useState(false)
  const [reminderBusyId, setReminderBusyId] = useState<string | null>(null)
  const [notFitId, setNotFitId] = useState<string | null>(null)
  const [remindId, setRemindId] = useState<string | null>(null)
  const [outreachId, setOutreachId] = useState<string | null>(null)

  const loadReminders = useCallback(async () => {
    try {
      setReminders(await getDueReminders())
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      setReminders([])
    }
  }, [navigate])

  const loadRuntimeStatus = useCallback(() => {
    if (!isApiMode && !isVerifiedPublicDemo) return
    void getRuntimeStatus().then((status) => {
      setRuntimeStatus(status)
      setRuntimeStatusChecked(true)
    })
  }, [])

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true)
      setError(null)
    }

    // Reminders and runtime health are auxiliary surfaces. Start them with the
    // main Today request, but never keep the primary page spinner waiting for
    // an extra cross-network round trip.
    void loadReminders()
    loadRuntimeStatus()

    try {
      const res = await todayActionsService.getTodayActions()
      let nextData: TodayActionsResponse = res
      if (!isApiMode && isVerifiedPublicDemo) {
        const { hydrateCachedAiDecisions } = await import('@/services/aiDecisionApi')
        const pool = res.opportunity_pool ?? res.cards
        const hydratedPool = await hydrateCachedAiDecisions(pool)
        const cards = hydratedPool
          .filter((card) => !shouldHideFromVerifiedTrialToday(card))
          .filter((card) => !localFeedbackHidesFromToday(card))
          .sort((left, right) =>
            localDiscoveryFeedbackBucket(left) - localDiscoveryFeedbackBucket(right) ||
            right.priority.score - left.priority.score ||
            left.rank - right.rank,
          )
          .slice(0, MAX_TODAY_CARDS)
          .map((card, index) => ({ ...card, rank: index + 1 }))
        nextData = {
          ...res,
          matched_count: hydratedPool.length,
          card_count: cards.length,
          opportunity_pool_count: hydratedPool.length,
          cards,
          opportunity_pool: hydratedPool,
        }
      } else if (isApiMode) {
        const { hydrateSharedAiDecisions } = await import('@/services/aiDecisionApi')
        const hydratedCards = await hydrateSharedAiDecisions(res.cards)
        const hydratedById = new Map(
          hydratedCards.map((card) => [card.opportunity_id, card]),
        )
        nextData = {
          ...res,
          cards: hydratedCards,
          opportunity_pool: res.opportunity_pool?.map(
            (card) => hydratedById.get(card.opportunity_id) ?? card,
          ),
        }
      }
      setData(nextData)
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      setError('今日行动加载失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [loadReminders, loadRuntimeStatus, navigate])

  useEffect(() => {
    void load()
  }, [load])

  const updateStatus = async (
    id: string,
    status: FollowupStatus,
    extra?: { reason?: string; remind_at?: string; note?: string },
  ) => {
    setBusyId(id)
    try {
      await todayActionsService.updateFollowup(id, { status, ...extra })
      await load(true)
      if (extra?.remind_at) toast('提醒已设置，当前销售阶段保持不变', 'success')
      else if (isApiMode) toast('跟进状态已同步服务器', 'success')
      else if (status === 'CONTACTED') toast('已联系，商机已移入“我的跟进”', 'success')
      else if (status === 'NOT_FIT') toast('已标记不适合，记录已保留在“我的跟进”', 'success')
      else toast('跟进状态已更新', 'success')
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('跟进状态更新失败，请重试')
    } finally {
      setBusyId(null)
    }
  }

  const analyzeOpportunity = async (id: string) => {
    const card = data?.cards.find((item) => item.opportunity_id === id)
    const automationUnavailableReason = runtimeAutomationUnavailableReason(
      runtimeStatus,
      runtimeStatusChecked,
      data?.refreshed_at ?? null,
    )
    if (!card || automationUnavailableReason || (!isApiMode && !isVerifiedPublicDemo)) return
    let aiApi: typeof import('@/services/aiDecisionApi') | null = null
    setAiBusyId(id)
    try {
      aiApi = await import('@/services/aiDecisionApi')
      const decision = await aiApi.requestAiDecision(card)
      setData((current) => {
        if (!current) return current
        const updateCard = (item: TodayActionCard) =>
          item.opportunity_id === id
            ? { ...item, model_decision_status: 'READY' as const, model_block_reason: null, decision }
            : item
        return {
          ...current,
          cards: current.cards.map(updateCard),
          opportunity_pool: current.opportunity_pool?.map(updateCard),
        }
      })
      toast('AI行动建议已生成', 'success')
    } catch (cause) {
      if (aiApi && cause instanceof aiApi.AiDecisionError && cause.code === 'AUTH_REQUIRED') {
        navigate('/login', { replace: true })
        return
      }
      if (aiApi && cause instanceof aiApi.AiDecisionError && cause.code === 'AI_NOT_CONFIGURED') {
        setRuntimeStatus((current) => current ? { ...current, ai: { configured: false } } : current)
      }
      toast(aiApi ? aiApi.aiDecisionErrorMessage(cause) : 'AI分析模块加载失败，请重试')
    } finally {
      setAiBusyId(null)
    }
  }

  const analyzeVisibleOpportunities = async () => {
    const automationUnavailableReason = runtimeAutomationUnavailableReason(
      runtimeStatus,
      runtimeStatusChecked,
      data?.refreshed_at ?? null,
    )
    const candidates = data?.cards.filter(
      (card) =>
        card.model_decision_status === 'AWAITING_MODEL' &&
        !card.decision,
    ) ?? []
    if (
      candidates.length === 0 ||
      automationUnavailableReason ||
      (!isApiMode && !isVerifiedPublicDemo)
    ) {
      return
    }

    let aiApi: typeof import('@/services/aiDecisionApi') | null = null
    setAiBatchBusy(true)
    try {
      aiApi = await import('@/services/aiDecisionApi')
      const result = await aiApi.requestAiDecisionBatch(candidates)
      const readyIds = Object.keys(result.decisions)
      if (readyIds.length > 0) {
        setData((current) => {
          if (!current) return current
          const updateCard = (item: TodayActionCard) => {
            const decision = result.decisions[item.opportunity_id]
            return decision
              ? {
                  ...item,
                  model_decision_status: 'READY' as const,
                  model_block_reason: null,
                  decision,
                }
              : item
          }
          return {
            ...current,
            cards: current.cards.map(updateCard),
            opportunity_pool: current.opportunity_pool?.map(updateCard),
          }
        })
      }

      const errorCount = Object.keys(result.errors).length
      if (readyIds.length > 0 && errorCount === 0) {
        toast(`AI已完成 ${readyIds.length} 条行动分析`, 'success')
      } else if (readyIds.length > 0) {
        toast(`已完成 ${readyIds.length} 条，另有 ${errorCount} 条未完成`)
      } else if (errorCount > 0) {
        const firstCode = Object.values(result.errors)[0]
        toast(aiApi.aiDecisionErrorMessage(new aiApi.AiDecisionError(firstCode, 502)))
      }
    } catch (cause) {
      if (aiApi && cause instanceof aiApi.AiDecisionError && cause.code === 'AUTH_REQUIRED') {
        navigate('/login', { replace: true })
        return
      }
      if (aiApi && cause instanceof aiApi.AiDecisionError && cause.code === 'AI_NOT_CONFIGURED') {
        setRuntimeStatus((current) => current ? { ...current, ai: { configured: false } } : current)
      }
      toast(aiApi ? aiApi.aiDecisionErrorMessage(cause) : 'AI批量分析模块加载失败，请重试')
    } finally {
      setAiBatchBusy(false)
    }
  }

  const acknowledgeReminder = async (reminderId: string) => {
    setReminderBusyId(reminderId)
    try {
      await acknowledgeDueReminder(reminderId)
      await load(true)
      toast('提醒已处理', 'success')
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('提醒处理失败，请重试')
    } finally {
      setReminderBusyId(null)
    }
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (!data) return <EmptyState title="暂无今日行动" hint="当前没有可展示的重点商机。" />

  const visibleCards =
    !isApiMode && isVerifiedPublicDemo
      ? data.cards.filter((card) => !shouldHideFromVerifiedTrialToday(card))
      : data.cards
  const visibleData = { ...data, card_count: visibleCards.length, cards: visibleCards }
  const poolCount = data.opportunity_pool_count ?? data.opportunity_pool?.length ?? data.matched_count
  const automationUnavailableReason = runtimeAutomationUnavailableReason(
    runtimeStatus,
    runtimeStatusChecked,
    data?.refreshed_at ?? null,
  )
  const aiUnavailableReason = automationUnavailableReason || (
    (isApiMode || isVerifiedPublicDemo) && runtimeStatus?.ai.configured === false
      ? AI_UNCONFIGURED_REASON
      : null
  )
  const snapshotWarning = runtimeSnapshotWarning(runtimeStatus, runtimeStatusChecked, data?.refreshed_at ?? null)
  const pendingAiCount = visibleCards.filter(
    (card) => card.model_decision_status === 'AWAITING_MODEL' && !card.decision,
  ).length

  return (
    <div className="space-y-3 sm:space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-3 py-3 shadow-sm sm:px-4 sm:py-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-3">
          <div>
            <h2 className="text-[17px] font-semibold text-slate-900 sm:text-lg">今天值得跟的医疗商机</h2>
            <p className="mt-1 text-[12px] leading-5 text-slate-500 sm:text-[13px] sm:leading-6">
              先看重点，再决定联系、跟进或按需让AI分析。
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500 sm:text-[12px]">
            <Clock className="h-3.5 w-3.5" />
            最近刷新 {formatDateTime(data.refreshed_at)}
          </div>
        </div>
        <div className="mt-2.5 flex flex-col gap-2 sm:mt-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-1.5 text-[11px] leading-5 text-slate-400">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{userCoverageWarning(data.coverage_warning)}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {(isApiMode || isVerifiedPublicDemo) && pendingAiCount > 0 ? (
              <button
                type="button"
                disabled={aiBatchBusy || Boolean(aiUnavailableReason)}
                onClick={() => void analyzeVisibleOpportunities()}
                title={aiUnavailableReason || '一次请求分析当前页面所有尚未分析的重点商机'}
                className="inline-flex self-start items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 text-[12px] font-medium text-indigo-800 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500"
              >
                {aiBatchBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                {aiBatchBusy ? '批量分析中' : `AI分析未分析项（${pendingAiCount}）`}
              </button>
            ) : null}
            {(isApiMode || isVerifiedPublicDemo) ? (
              <button
                type="button"
                onClick={() => navigate('/intent-followup')}
                title="按需加载完整商机池，核查采购意向及可能的后续正式公告"
                className="inline-flex self-start items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[12px] font-medium text-amber-800 hover:bg-amber-100"
              >
                <Radar className="h-3.5 w-3.5" />
                采购意向跟进
              </button>
            ) : null}
            {(isApiMode || isVerifiedPublicDemo) && poolCount > visibleCards.length ? (
              <button
                type="button"
                onClick={() => navigate('/opportunities')}
                className="self-start rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[12px] font-medium text-teal-800 hover:bg-teal-100"
              >
                查看全部 {poolCount} 条
              </button>
            ) : null}
          </div>
        </div>
      </section>

      {snapshotWarning ? (
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12px] leading-5 text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{snapshotWarning}</span>
        </div>
      ) : null}

      {!isApiMode && isVerifiedPublicDemo ? (
        <div className="flex flex-wrap items-center gap-2 px-1 text-[11px] text-slate-500">
          <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">业务地区：{marketSelectionLabel()}</span>
          <span>每条商机可查看官方依据</span>
          {runtimeStatus?.ai.configured ? (
            <span className="rounded-full border border-indigo-100 bg-indigo-50 px-2.5 py-1 text-indigo-700">AI可用</span>
          ) : runtimeStatus?.ai.configured === false ? (
            <span className="rounded-full border border-amber-100 bg-amber-50 px-2.5 py-1 text-amber-700">AI建议按需加载</span>
          ) : null}
        </div>
      ) : null}

      <DueRemindersPanel
        reminders={reminders}
        currentOpportunityIds={visibleCards.map((card) => card.opportunity_id)}
        busyId={reminderBusyId}
        onOpenToday={(opportunityId) => navigate(`/opportunity/${opportunityId}`)}
        onOpenFollowed={(opportunityId) => navigate(`/followed?focus=${encodeURIComponent(opportunityId)}`)}
        onAcknowledge={(reminderId) => void acknowledgeReminder(reminderId)}
      />

      <MetricCards data={visibleData} />

      {visibleCards.length === 0 ? (
        <EmptyState title="今日暂无重点行动" hint="当前重点已处理，或暂无需要今天采取行动的项目。" />
      ) : (
        <div className="space-y-3">
          {visibleCards.map((card) => (
            <ActionCard
              key={card.opportunity_id}
              card={card}
              busy={busyId === card.opportunity_id}
              aiBusy={aiBusyId === card.opportunity_id}
              onDetail={() => navigate(`/opportunity/${card.opportunity_id}`)}
              onContacted={() => void updateStatus(card.opportunity_id, 'CONTACTED')}
              onFollow={() => void updateStatus(card.opportunity_id, 'REVIEWING')}
              onNotFit={() => setNotFitId(card.opportunity_id)}
              onRemind={() => setRemindId(card.opportunity_id)}
              onOutreach={() => {
                if (!automationUnavailableReason) setOutreachId(card.opportunity_id)
              }}
              onAnalyze={isApiMode || isVerifiedPublicDemo ? () => void analyzeOpportunity(card.opportunity_id) : undefined}
              onFeedbackChanged={() => load(true)}
              analysisUnavailableReason={aiUnavailableReason}
              automationUnavailableReason={automationUnavailableReason}
            />
          ))}
        </div>
      )}

      <NotFitModal
        open={Boolean(notFitId)}
        onClose={() => setNotFitId(null)}
        onConfirm={(reason: NotFitReason) => {
          if (!notFitId) return
          const id = notFitId
          setNotFitId(null)
          void updateStatus(id, 'NOT_FIT', { reason })
        }}
      />
      <RemindModal
        open={Boolean(remindId)}
        onClose={() => setRemindId(null)}
        onConfirm={(remindAt, nextAction) => {
          if (!remindId || !data) return
          const id = remindId
          const currentCard = (data.opportunity_pool ?? data.cards).find(
            (item) => item.opportunity_id === id,
          )
          setRemindId(null)
          void updateStatus(id, currentCard?.followup_status ?? 'NEW', {
            remind_at: remindAt,
            note: nextAction
              ? `下次行动：${nextAction}`
              : '设置下次跟进提醒；销售阶段保持不变。',
          })
        }}
      />
      {outreachId ? (
        <Suspense fallback={null}>
          <OutreachDrawer open opportunityId={outreachId} onClose={() => setOutreachId(null)} />
        </Suspense>
      ) : null}
    </div>
  )
}
